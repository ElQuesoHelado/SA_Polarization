from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..common import LABELS, atomic_json, read_csv
from ..learning import classification_metrics
from ..metrics import holm
from .analysis import number
from .annotations import close_reference, decisions
from .state import output, seal, verify, verify_seal

MODEL_IDS = ("robertuito", "beto", "bertin", "xlm_roberta")


def joined_reference(sample, prediction):
    truth = []
    for row in sample.to_dict("records"):
        for item in json.loads(row["annotation_json"]):
            truth.append(dict(comment_id=row["comment_id"], target_id=item["target_id"], label=item["valence"], gold_target_present=True))
    gold = pd.DataFrame(truth, columns=["comment_id", "target_id", "label", "gold_target_present"])
    if gold.duplicated(["comment_id", "target_id"]).any():
        raise ValueError("Referencia con objetivos repetidos")
    prediction = prediction.loc[prediction.comment_id.isin(set(sample.comment_id))].copy()
    prediction["candidate_present"] = True
    if prediction.duplicated(["comment_id", "target_id"]).any():
        raise ValueError("Predicciones duplicadas")
    frame = gold.merge(prediction, on=["comment_id", "target_id"], how="outer", validate="one_to_one")
    frame["label"] = frame.label.fillna("not_evaluable")
    frame["valence"] = frame.valence.fillna("omitted")
    frame["accepted"] = frame.accepted.fillna(False).astype(str).str.lower().eq("true")
    frame["context_complete"] = frame.context_complete.fillna(False).astype(str).str.lower().eq("true")
    for key in ("gold_target_present", "candidate_present"):
        frame[key] = frame[key].fillna(False).astype(bool)
    meta = sample.set_index("comment_id")
    frame["post_id"] = frame.comment_id.map(meta.post_id)
    frame["weight"] = frame.comment_id.map(1 / meta.sampling_probability.astype(float))
    return frame


def measure(frame, weights=None):
    weights = frame.weight.to_numpy(dtype=float) if weights is None else np.asarray(weights, dtype=float)
    raw = classification_metrics(frame.label, frame.valence, weights)
    accepted = frame.accepted.to_numpy(dtype=bool)
    evaluable = frame.label.isin(LABELS[:3]).to_numpy()
    covered = accepted & frame.valence.isin(LABELS[:3]).to_numpy() & evaluable
    result = dict(macro_f1=raw["macro_f1"], coverage=float(weights[covered].sum()/weights[evaluable].sum()) if weights[evaluable].sum() else np.nan)
    for label in ("positive", "negative"):
        chosen = accepted & frame.valence.eq(label).to_numpy()
        result[label+"_precision"] = float(weights[chosen & frame.label.eq(label).to_numpy()].sum()/weights[chosen].sum()) if weights[chosen].sum() else np.nan
        result[label+"_accepted_n"] = int(chosen.sum())
    return result


def compare(settings, plan, study, registry, *, stage="provisional"):
    verify(study, frozen=True)
    manifest = verify_seal(study / "predictions")
    if not manifest.get("diagnostic_only"):
        raise ValueError("Se requieren predicciones diagnósticas identificadas")
    from ..common import sha256
    if (manifest["prediction_input_sha256"] != sha256(study / "prediction_input.csv")
            or manifest["prediction_scope_sha256"] != sha256(study / "prediction_scope.csv")):
        raise ValueError("La entrada o alcance de predicción cambiaron")
    sample = decisions(study, "benchmark", registry, stage)
    inputs = read_csv(study / "prediction_input.csv")
    expected = inputs.loc[inputs.comment_id.isin(set(sample.comment_id)), ["comment_id", "target_id", "post_id"]]
    expected_keys = set(expected.itertuples(index=False, name=None))
    frames, comparisons = {}, []
    all_predictions = {}
    for model_id in MODEL_IDS:
        prediction = read_csv(study / "predictions" / f"{model_id}.csv")
        prediction = prediction.loc[prediction.comment_id.isin(set(sample.comment_id))].copy()
        if set(prediction.model_id) != {model_id} or set(prediction[["comment_id", "target_id", "post_id"]].itertuples(index=False, name=None)) != expected_keys:
            raise ValueError("Predicciones incompletas o identidades alteradas")
        all_predictions[model_id] = prediction
        frames[model_id] = joined_reference(sample, prediction)
    # Conditional common-context panel; extraction omissions remain in the full end-to-end report.
    common_keys = None
    for prediction in all_predictions.values():
        valid = prediction.loc[prediction.context_complete.str.lower().eq("true")]
        keys = set(zip(valid.comment_id, valid.target_id))
        common_keys = keys if common_keys is None else common_keys & keys
    for model_id, frame in frames.items():
        point = measure(frame)
        common = frame.loc[[key in common_keys for key in zip(frame.comment_id, frame.target_id)]]
        comparisons.append(dict(model_id=model_id, panel="end_to_end", pairs=len(frame), **point))
        comparisons.append(dict(model_id=model_id, panel="common_complete_candidates", pairs=len(common), **measure(common)))
    from ..registry import load_registry
    target_groups = {t["target_id"]: t["target_group"] for t in load_registry(registry)["targets"]}
    stratified = []
    meta = sample.set_index("comment_id")
    for model_id, frame in frames.items():
        groups = {"target_group": frame.target_id.map(target_groups).fillna("unknown"),
                  "source_party": frame.comment_id.map(meta.party),
                  "comment_type": frame.comment_id.map(meta.comment_type)}
        for dimension, values in groups.items():
            for value in sorted(values.unique()):
                subset = frame.loc[values.eq(value)]
                stratified.append(dict(model_id=model_id, dimension=dimension, value=value, pairs=len(subset),
                                       low_support=len(subset)<10, **measure(subset)))
    rng = np.random.default_rng(plan["selection_seed"])
    videos = sample.post_id.unique()
    draws = {model: [] for model in MODEL_IDS}
    for _ in range(plan["bootstrap_iterations"]):
        counts = rng.multinomial(len(videos), np.full(len(videos), 1/len(videos)))
        mapping = dict(zip(videos, counts))
        for model_id, frame in frames.items():
            weights = frame.weight.to_numpy(dtype=float) * frame.post_id.map(mapping).to_numpy(dtype=float)
            draws[model_id].append(measure(frame, weights))
    intervals, contrasts = [], []
    for model_id in MODEL_IDS:
        point = measure(frames[model_id])
        for metric in ("macro_f1", "coverage", "positive_precision", "negative_precision"):
            values = np.array([draw[metric] for draw in draws[model_id]])
            values = values[np.isfinite(values)]
            sufficient = len(values) >= max(10, .8*plan["bootstrap_iterations"])
            low, high = np.quantile(values, [.025, .975]) if sufficient else (np.nan, np.nan)
            intervals.append(dict(model_id=model_id, metric=metric, estimate=number(point[metric]),
                ci_low=number(low), ci_high=number(high), valid_replicates=len(values),
                status="estimated" if sufficient else "insufficient_support"))
    for i, left in enumerate(MODEL_IDS):
        for right in MODEL_IDS[i+1:]:
            difference = measure(frames[left])["macro_f1"]-measure(frames[right])["macro_f1"]
            values = np.array([a["macro_f1"]-b["macro_f1"] for a, b in zip(draws[left], draws[right])])
            low, high = np.quantile(values, [.025, .975])
            p = (1+np.sum(np.abs(values-difference) >= abs(difference)))/(len(values)+1)
            contrasts.append(dict(left=left, right=right, macro_f1_difference=difference, ci_low=float(low), ci_high=float(high), p=float(p)))
    for row, p in zip(contrasts, holm([r["p"] for r in contrasts])):
        row["p_holm"] = p
    destination = output(settings, study) / f"benchmark_{stage}"
    destination.mkdir(exist_ok=False)
    pd.DataFrame(comparisons).to_csv(destination / "comparison.csv", index=False)
    pd.DataFrame(intervals).to_csv(destination / "intervals.csv", index=False)
    pd.DataFrame(contrasts).to_csv(destination / "model_contrasts.csv", index=False)
    pd.DataFrame(stratified).to_csv(destination / "stratified_performance.csv", index=False)
    for model, frame in frames.items():
        frame.to_csv(destination / f"{model}_pairs.csv", index=False)
        frame.groupby(["label", "valence"], sort=True).weight.sum().reset_index().to_csv(destination / f"{model}_confusion.csv", index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    compared = pd.DataFrame(comparisons).query("panel == 'end_to_end'").set_index("model_id")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for axis, metric in zip(axes, ("macro_f1", "coverage")):
        axis.bar(compared.index, compared[metric]); axis.set_ylim(0, 1); axis.set_title(metric); axis.tick_params(axis="x", rotation=25)
    fig.savefig(destination / "comparison.png", dpi=200, bbox_inches="tight"); plt.close(fig)
    cohort_comparison(settings, study, registry, stage, destination)
    # Historical general sentiment is compared only on exactly the same available subset.
    baseline_comments = sample.loc[sample.sentimiento.isin(LABELS[:3])] if "sentimiento" in sample else sample.iloc[:0]
    if len(baseline_comments):
        baseline = all_predictions["beto"].loc[all_predictions["beto"].comment_id.isin(set(baseline_comments.comment_id))].copy()
        baseline["valence"] = baseline.comment_id.map(baseline_comments.set_index("comment_id").sentimiento)
        baseline["accepted"], baseline["context_complete"] = True, True
        matched = joined_reference(baseline_comments, baseline)
        result = [{"model_id": "historical_general_sentiment", "comments": len(baseline_comments), "pairs": len(matched), **measure(matched)}]
        for model, pred in all_predictions.items():
            matched = joined_reference(baseline_comments, pred)
            result.append({"model_id": model, "comments": len(baseline_comments), "pairs": len(matched), **measure(matched)})
        pd.DataFrame(result).to_csv(destination / "historical_baseline_matched.csv", index=False)
    summary = dict(stage=stage, comments=len(sample), evaluated_models=list(MODEL_IDS),
        reference="ai_proposals_agreement_only" if stage == "provisional" else "single_human_blind",
        model_selected_for_production=None, reserved_test_opened=False,
        limitation="Provisional compara acuerdo con IA, no exactitud humana" if stage == "provisional" else "Referencia de un humano; incertidumbre condicional al marco de videos")
    extraction = frames["beto"]
    tp = extraction.loc[extraction.gold_target_present & extraction.candidate_present, "weight"].sum()
    predicted = extraction.loc[extraction.candidate_present, "weight"].sum()
    actual = extraction.loc[extraction.gold_target_present, "weight"].sum()
    summary["extraction_precision"] = number(tp/predicted) if predicted else None
    summary["extraction_recall"] = number(tp/actual) if actual else None
    atomic_json(destination / "summary.json", summary)
    (destination / "report.md").write_text("# Comparación de cuatro modelos\n\n"+json.dumps(summary, ensure_ascii=False, indent=2)+
        "\n\ncomparison.csv separa evaluación integral y candidatos de contexto completo común.\n"+
        "Los intervalos remuestrean videos; los seis contrastes macro-F1 usan Holm. Ningún resultado habilita producción.\n")
    if stage == "final":
        close_reference(study, "benchmark", registry)
    seal(destination, [p.name for p in destination.iterdir() if p.is_file()], status="complete", stage=stage)
    verify(study, frozen=True)
    return destination


def cohort_comparison(settings, study, registry, stage, destination):
    """Measurement error on full annotated histories; explicitly not independent prediction accuracy."""
    from .annotations import cohort_samples
    from .analysis import events_from_annotations, scores
    from ..metrics import collapse_events
    from ..registry import load_registry
    if not list((study / "annotations").glob("cohort_*/sample.csv")):
        return
    sample = cohort_samples(study, registry, stage)
    scope = set(read_csv(study / "prediction_scope.csv").comment_id)
    if not set(sample.comment_id) <= scope:
        (destination / "cohort_not_scored.txt").write_text("Hay historiales fuera del trabajo de predicción; no se imputaron abstenciones ni errores.\n")
        return
    gold = scores(events_from_annotations(sample, registry), settings).set_index("user_id")
    targets = {t["target_id"]: t["target_group"] for t in load_registry(registry)["targets"]}
    results = []
    for model_id in MODEL_IDS:
        pred = read_csv(study / "predictions" / f"{model_id}.csv")
        pred = pred.loc[pred.comment_id.isin(set(sample.comment_id))].copy()
        pred = pred.drop(columns=["post_id", "sample_id", "model_id"])
        metadata = sample[["comment_id", "post_id", "user_id", "channel_id", "party", "comment_published_at"]]
        pred = pred.merge(metadata, on="comment_id", how="left", validate="many_to_one")
        pred["target_group"] = pred.target_id.map(targets)
        pred["corpus"] = "publication_union"
        estimate = scores(collapse_events(pred), settings).set_index("user_id")
        users = pd.Index(sample.user_id.unique(), name="user_id")
        left, right = gold.reindex(users), estimate.reindex(users)
        paired = left.paired.eq(True) & right.paired.eq(True)
        determined = left.ingroup.fillna("Undetermined").eq(right.ingroup.fillna("Undetermined"))
        results.append(dict(model_id=model_id, users=len(users), gold_comparable=int(left.paired.eq(True).sum()),
            predicted_comparable=int(right.paired.eq(True).sum()), both_comparable=int(paired.sum()),
            affinity_agreement=float(determined.mean()), gap_mae=number((left.loc[paired,"gap"]-right.loc[paired,"gap"]).abs().mean()),
            AP_mae=number((left.loc[paired,"AP_target"]-right.loc[paired,"AP_target"]).abs().mean()),
            gap_sign_disagreement=number((np.sign(left.loc[paired,"gap"]) != np.sign(right.loc[paired,"gap"])).mean()) if paired.any() else None,
            independent_predictive_evaluation=False))
    pd.DataFrame(results).to_csv(destination / "cohort_measurement_errors.csv", index=False)
