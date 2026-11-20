"""Local diagnostics of frozen development predictions; never trains or selects models."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..common import LABELS, atomic_json, read_csv, sha256
from ..diagnostics import load_development, weight_summary
from ..learning import classification_metrics, probabilities
from ..registry import load_registry
from .state import output, seal, verify, verify_seal
from .training_report import summarize

MODELS = ("robertuito", "beto", "bertin", "xlm_roberta")
KEYS = ["comment_id", "target_id"]


def align_pairs(frame, keys):
    if frame.duplicated(KEYS).any() or keys.duplicated(KEYS).any():
        raise ValueError("Pares de desarrollo duplicados")
    result = keys.merge(frame, on=KEYS, how="left", sort=False, validate="one_to_one", indicator=True)
    if not result._merge.eq("both").all():
        raise ValueError("Pares comunes ajenos al desarrollo")
    return result.drop(columns="_merge")


def prediction_details(frame, logits, calibration):
    # Includes shape, seed-count, finite-values and weight validation.
    metrics = summarize(frame.label, frame.weight, logits, calibration)
    mean = np.mean([probabilities(v) for v in logits], axis=0)
    probs = probabilities(np.log(mean.clip(1e-12)), calibration["temperature"])
    result = frame.copy()
    result["predicted_label"] = np.array(LABELS)[probs.argmax(axis=1)]
    result["confidence"] = probs.max(axis=1)
    result["threshold"] = result.predicted_label.map(calibration["thresholds"])
    result["accepted"] = result.confidence >= result.threshold
    result["correct"] = result.predicted_label.eq(result.label)
    result["status"] = np.where(result.accepted & result.predicted_label.isin(LABELS[:3]), "accepted",
        np.where(result.accepted, "accepted_auxiliary", "low_confidence"))
    for index, label in enumerate(LABELS):
        result["p_"+label] = probs[:, index]
    return result, metrics


def scope_reference(development, validation, common):
    gold = []
    for row in development.loc[development.split.eq("validation")].to_dict("records"):
        for item in row["items"]:
            gold.append(dict(comment_id=row["comment_id"], target_id=item["target_id"], reference_label=item["valence"]))
    gold = pd.DataFrame(gold, columns=[*KEYS, "reference_label"])
    if gold.duplicated(KEYS).any() or validation.duplicated(KEYS).any():
        raise ValueError("Referencia o candidatos duplicados")
    gold["gold_target_present"] = True
    candidates = validation[KEYS].assign(candidate_present=True)
    scope = gold.merge(candidates, on=KEYS, how="outer", validate="one_to_one")
    scope["gold_target_present"] = scope.gold_target_present.fillna(False).astype(bool)
    scope["candidate_present"] = scope.candidate_present.fillna(False).astype(bool)
    scope["reference_label"] = scope.reference_label.fillna("not_evaluable")
    common_keys = set(common[KEYS].itertuples(index=False, name=None))
    scope["common_context"] = [k in common_keys for k in scope[KEYS].itertuples(index=False, name=None)]
    meta = development.loc[development.split.eq("validation")].set_index("comment_id")
    if meta.index.duplicated().any() or not scope.comment_id.isin(meta.index).all():
        raise ValueError("Metadata de validación incompatible")
    for name in ("post_id", "text", "weight", "party", "comment_type", "comment_published_at"):
        if name in meta:
            scope[name] = scope.comment_id.map(meta[name])
    return scope


def coverage_rows(frame, model):
    rows = []
    weight = frame.weight.astype(float)
    gold = frame.gold_target_present & frame.reference_label.isin(LABELS[:3])
    denominator = float(weight[gold].sum())
    for status in ("missed_target", "outside_common_context_panel", "low_confidence", "accepted_auxiliary", "accepted"):
        selected = gold & frame.status.eq(status)
        rows.append(dict(model=model, status=status, evaluable_gold_pairs=int(selected.sum()),
            weight=float(weight[selected].sum()), evaluable_gold_weight=denominator,
            weighted_share=float(weight[selected].sum()/denominator) if denominator else None,
            denominator="all human evaluable validation targets; scores only on shared common-context panel"))
    return rows


def diagnose(settings, plan, parent, study, registry):
    verify(study)
    verify_seal(study / "training_input")
    verify_seal(study / "training")
    destination = output(settings, study) / "development_diagnostics"
    if destination.exists():
        raise FileExistsError("Diagnóstico existente; no sobrescribir")
    source = study / "training"
    stored = json.loads((source / "comparison.json").read_text())
    if stored["completed_fits"] != 12 or stored["production_enabled"] is not False or tuple(m["model_id"] for m in stored["models"]) != MODELS:
        raise ValueError("Comparación de desarrollo incompatible")
    closure = json.loads((parent / "annotations/manifest.json").read_text())
    if closure.get("status") != "human_reviewed_assisted" or closure.get("gold_sha256") != sha256(parent / "annotations/gold.csv"):
        raise ValueError("Referencia de desarrollo sin cierre íntegro")
    development, provenance = load_development(parent)  # skips test before JSON decoding
    validation = read_csv(study / "training_input/validation.csv")
    training = read_csv(study / "training_input/train.csv")
    if not validation.split.eq("validation").all() or not training.split.eq("train").all():
        raise ValueError("Particiones de desarrollo incompatibles")
    common_keys = read_csv(source / "shared_validation_pairs.csv")
    shared = align_pairs(validation, common_keys)
    shared_train = align_pairs(training, read_csv(source / "shared_training_pairs.csv"))
    scope = scope_reference(development, validation, shared)
    reference_check = shared[KEYS+["label"]].merge(scope[KEYS+["reference_label"]],on=KEYS,validate="one_to_one")
    if not reference_check.label.eq(reference_check.reference_label).all():
        raise ValueError("Las etiquetas de entrada no coinciden con la referencia humana")
    targets = {r["target_id"]: r for r in load_registry(registry, frozen=True)["targets"]}
    scope["target_group"] = scope.target_id.map(lambda k: targets.get(k, {}).get("target_group", "unknown"))
    scope["target_name"] = scope.target_id.map(lambda k: targets.get(k, {}).get("name", k))
    support = []
    for name, frame in (("train_candidates", training), ("train_common", shared_train), ("validation_candidates", validation), ("validation_common", shared)):
        for label in LABELS:
            selected = frame.loc[frame.label.eq(label)]
            support.append(dict(scope=name, label=label, **weight_summary(selected.weight.astype(float))))
    models, seed_rows, confusion, performance, curves, inventories, breakdown = {}, [], [], [], [], [], []
    for item in stored["models"]:
        name = item["model_id"]
        folder = source / name / "model"
        manifest = json.loads((folder / "training_manifest.json").read_text())
        if (manifest["shared_validation_pairs_sha256"] != sha256(source / "shared_validation_pairs.csv")
                or [r["seed"] for r in manifest["revisions"]] != [42, 43, 44]):
            raise ValueError("Subconjunto/semillas del modelo incompatibles")
        logits = [np.load(folder / f"validation_logits_{seed}.npy", allow_pickle=False) for seed in (42, 43, 44)]
        detail, result = prediction_details(shared, logits, manifest["calibration"])
        if not np.isclose(result["metrics"]["macro_f1"], item["metrics"]["macro_f1"], atol=1e-10, rtol=0):
            raise ValueError("El diagnóstico no reproduce el macro-F1 remoto")
        result["unweighted_metrics"] = classification_metrics(detail.label, detail.predicted_label)
        models[name] = result
        for seed, values in zip((42, 43, 44), logits):
            predicted = np.array(LABELS)[values.argmax(axis=1)]
            seed_rows.append(dict(model=name, seed=seed, macro_f1_weighted=classification_metrics(detail.label, predicted, detail.weight.astype(float))["macro_f1"],
                macro_f1_unweighted=classification_metrics(detail.label, predicted)["macro_f1"]))
        full = scope.merge(detail[[*KEYS, "predicted_label", "confidence", "threshold", "accepted", "correct", "status", *["p_"+l for l in LABELS]]],
            on=KEYS, how="left", validate="one_to_one")
        full["status"] = np.where(~full.candidate_present, "missed_target", np.where(~full.common_context, "outside_common_context_panel", full.status))
        full["accepted"] = full.accepted.fillna(False).astype(bool)
        full["predicted_label"] = full.predicted_label.fillna("not_scored")
        full["model"] = name
        inventories.append(full)
        breakdown.extend(coverage_rows(full, name))
        for true in LABELS:
            for pred in LABELS:
                mask = detail.label.eq(true) & detail.predicted_label.eq(pred)
                confusion.append(dict(model=name, reference=true, predicted=pred, pairs=int(mask.sum()), weight=float(detail.loc[mask, "weight"].astype(float).sum())))
        meta = full.set_index(KEYS)
        tagged = detail.copy()
        for dim in ("target_group", "party", "comment_type"):
            if dim in full:
                tagged[dim] = [meta.loc[key, dim] for key in tagged[KEYS].itertuples(index=False, name=None)]
        for dim in ("target_id", "target_group", "party", "comment_type"):
            if dim not in tagged:
                continue
            for value, part in tagged.groupby(dim, sort=True):
                metrics = classification_metrics(part.label, part.predicted_label, part.weight.astype(float))
                performance.append(dict(model=name, dimension=dim, value=value, pairs=len(part), low_support=len(part)<10,
                    macro_f1_weighted=metrics["macro_f1"], macro_f1_unweighted=classification_metrics(part.label, part.predicted_label)["macro_f1"],
                    **{"support_"+label:metrics["classes"][label]["support"] for label in LABELS}))
        weights = detail.weight.astype(float).to_numpy()
        for label in LABELS:
            gold = detail.label.eq(label).to_numpy()
            for threshold in sorted(set([*np.round(np.arange(.5,1,.05),2), manifest["calibration"]["thresholds"][label], 1.01])):
                chosen = detail.predicted_label.eq(label).to_numpy() & (detail.confidence.to_numpy() >= threshold)
                tp = weights[chosen & gold].sum()
                curves.append(dict(model=name, label=label, threshold=float(threshold), selected_pairs=int(chosen.sum()),
                    weighted_precision=float(tp/weights[chosen].sum()) if chosen.any() else None,
                    weighted_recall=float(tp/weights[gold].sum()) if gold.any() else None,
                    candidate_pair_coverage=float(weights[chosen].sum()/weights.sum()),
                    saved_operating_point=bool(np.isclose(threshold, manifest["calibration"]["thresholds"][label]))))
    destination.mkdir()
    scope.to_csv(destination / "validation_scope.csv", index=False)
    inventory = pd.concat(inventories, ignore_index=True)
    inventory.to_csv(destination / "error_inventory.csv", index=False)
    pd.DataFrame(support).to_csv(destination / "class_support.csv", index=False)
    pd.DataFrame(seed_rows).to_csv(destination / "seeds.csv", index=False)
    pd.DataFrame(confusion).to_csv(destination / "confusion.csv", index=False)
    pd.DataFrame(performance).to_csv(destination / "stratified_performance.csv", index=False)
    pd.DataFrame(curves).to_csv(destination / "precision_coverage.csv", index=False)
    pd.DataFrame(breakdown).to_csv(destination / "coverage_breakdown.csv", index=False)
    summary = dict(models=models, weight_diagnostics=weight_summary(shared.weight.astype(float)),
        training_input_sha256=sha256(study / "training_input/manifest.json"), training_sha256=sha256(source / "manifest.json"),
        development_provenance=provenance, reference_sha256=sha256(parent / "annotations/gold.csv"),
        development_only=True, production_enabled=False, calibration_changed=False,
        train_common=len(shared_train), validation_common=len(shared), validation_candidate_pairs=len(validation),
        validation_human_targets=int(scope.gold_target_present.sum()),
        extraction_missed_targets=int((scope.gold_target_present & ~scope.candidate_present).sum()),
        context_excluded_candidates=int((scope.candidate_present & ~scope.common_context).sum()))
    summary["scoring_scope"] = "Stored logits score only the common complete-context panel. Other candidates are unscored, not necessarily overlong for every model. This is not each model's full inference coverage."
    atomic_json(destination / "summary.json", summary)
    _plots(destination, pd.DataFrame(curves), inventory)
    text = ["# Diagnóstico de desarrollo", "", "Referencia de desarrollo reutilizada/asistida; no evaluación independiente. No modifica calibración, etiquetas o modelos.", "",
        f"Pares comunes: {len(shared_train)} de entrenamiento y {len(shared)} de validación. Objetivos humanos de validación: {summary['validation_human_targets']}; omitidos por extracción: {summary['extraction_missed_targets']}; candidatos excluidos del panel común: {summary['context_excluded_candidates']}.", "",
        "| Modelo | Macro-F1 ponderado | Sin ponderar | F1 neutral | Predicciones neutrales antes de abstener |",
        "|---|---:|---:|---:|---:|"]
    for name, result in models.items():
        neutral = inventory.loc[inventory.model.eq(name) & inventory.common_context & inventory.predicted_label.eq("neutral")]
        text.append(f"| {name} | {result['metrics']['macro_f1']:.4f} | {result['unweighted_metrics']['macro_f1']:.4f} | {result['metrics']['classes']['neutral']['f1']:.4f} | {len(neutral)} |")
    text += ["", f"N efectivo debido solo a pesos: {summary['weight_diagnostics']['effective_n_weights_only']:.2f}; no incorpora dependencia por usuario, video o canal.", "",
        "Los conteos y confusiones documentan errores; no identifican por sí solos causas lingüísticas, errores humanos o beneficios de otro entrenamiento. La variación entre semillas no es replicación independiente.", "",
        "coverage_breakdown.csv usa todos los objetivos humanos evaluables de validación, pero solo hay puntuaciones del panel común. Los candidatos fuera de él no necesariamente exceden el contexto de cada modelo: no fueron puntuados en esta comparación. Este desglose no estima la cobertura de una inferencia completa propia de cada modelo. Las curvas usan candidatos comunes y no reemplazan ese denominador. Son descriptivas: no seleccionan otros umbrales. Estratos de menos de diez pares se marcan con soporte bajo.", "",
        "error_inventory.csv contiene texto y referencia: conservar localmente; no publicar automáticamente. Los campos vacíos de confianza en omisiones/contexto son ausencia de puntuación, no confianza cero.", ""]
    (destination / "report.md").write_text("\n".join(text))
    seal(destination, [p.name for p in destination.iterdir() if p.is_file()], diagnostic_only=True)
    verify(study)
    return destination


def _plots(destination, curves, inventory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10,4))
    for model in MODELS:
        curve = curves.loc[curves.model.eq(model) & curves.label.eq("neutral")]
        axes[0].plot(curve.candidate_pair_coverage, curve.weighted_precision, marker=".", label=model)
        part = inventory.loc[inventory.model.eq(model) & inventory.common_context]
        axes[1].hist(part.confidence, bins=np.linspace(0,1,11), histtype="step", label=model)
    axes[0].set(xlabel="Cobertura de pares candidatos (neutral)", ylabel="Precisión ponderada", ylim=(0,1.05))
    axes[1].set(xlabel="Confianza calibrada", ylabel="Pares comunes")
    for ax in axes: ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(destination / "diagnostics.png", dpi=180); plt.close(fig)
