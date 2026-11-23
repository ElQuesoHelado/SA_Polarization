"""Recompute development diagnostics from frozen logits, without GPU or test labels."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..common import LABELS, atomic_json, read_csv, sha256, stamp
from ..learning import classification_metrics, probabilities
from .state import output, seal, verify, verify_seal


def summarize(truth, weights, logits, calibration):
    """Match predict_worker: average seed probabilities, then temperature/thresholds."""
    truth, weights = np.asarray(truth), np.asarray(weights, dtype=float)
    if (not len(truth) or weights.shape != truth.shape or not np.isfinite(weights).all()
            or (weights <= 0).any()):
        raise ValueError("Referencia/pesos de desarrollo inválidos")
    if len(logits) != 3 or any(v.shape != (len(truth), len(LABELS)) or not np.isfinite(v).all() for v in logits):
        raise ValueError("Se requieren logits íntegros de las tres semillas")
    mean = np.mean([probabilities(v) for v in logits], axis=0)
    uncalibrated = np.array(LABELS)[mean.argmax(axis=1)]
    calibrated = probabilities(np.log(mean.clip(1e-12)), calibration["temperature"])
    predicted = np.array(LABELS)[calibrated.argmax(axis=1)]
    accepted = calibrated.max(axis=1) >= np.array([calibration["thresholds"][v] for v in predicted])
    accepted_valence = accepted & np.isin(predicted, LABELS[:3])
    evaluable = np.isin(truth, LABELS[:3])
    classes = {}
    for label in LABELS:
        mask = accepted & (predicted == label)
        classes[label] = dict(accepted_pairs=int(mask.sum()), accepted_weight=float(weights[mask].sum()),
            precision=float(np.average(truth[mask] == label, weights=weights[mask])) if mask.any() else None,
            threshold=calibration["thresholds"][label])
    return dict(metrics=classification_metrics(truth, uncalibrated, weights),
        candidate_pair_coverage=float(weights[accepted_valence].sum() / weights.sum()),
        evaluable_candidate_coverage=float(weights[accepted_valence & evaluable].sum() / weights[evaluable].sum()) if evaluable.any() else None,
        accepted_valence_pairs=int(accepted_valence.sum()), abstained_pairs=int((~accepted).sum()),
        accepted_auxiliary_pairs=int((accepted & ~accepted_valence).sum()),
        classes=classes, calibration=calibration,
        seeds=[classification_metrics(truth, np.array(LABELS)[v.argmax(axis=1)], weights) for v in logits])


def report(settings, study):
    verify(study)
    verify_seal(study / "training_input")
    verify_seal(study / "training")
    root = study / "training"
    stored = json.loads((root / "comparison.json").read_text())
    input_plan_path = study / "training_input/plan.json"
    input_plan = json.loads(input_plan_path.read_text()) if input_plan_path.exists() else {"maximum_fits": 12}
    expected_fits = input_plan["maximum_fits"]
    if expected_fits not in (6, 12):
        raise ValueError("Presupuesto de ajustes incompatible")
    if stored["completed_fits"] != expected_fits or stored["production_enabled"] is not False:
        raise ValueError("Comparación incompleta o incompatible")
    validation = read_csv(study / "training_input/validation.csv")
    pairs = read_csv(root / "shared_validation_pairs.csv")
    keys = ["comment_id", "target_id"]
    if validation.duplicated(keys).any() or pairs.duplicated(keys).any():
        raise ValueError("Pares de validación duplicados")
    shared = pairs.merge(validation, on=keys, how="left", sort=False, validate="one_to_one", indicator=True)
    if not shared._merge.eq("both").all() or not shared.split.eq("validation").all():
        raise ValueError("Subconjunto común incompatible con validación")
    models, rows = {}, []
    for item in stored["models"]:
        name = item["model_id"]
        folder = root / name / "model"
        manifest = json.loads((folder / "training_manifest.json").read_text())
        if manifest["shared_validation_pairs_sha256"] != sha256(root / "shared_validation_pairs.csv"):
            raise ValueError("El modelo utilizó otro subconjunto de validación")
        if [r["seed"] for r in manifest["revisions"]] != [42, 43, 44]:
            raise ValueError("Semillas inesperadas")
        logits = [np.load(folder / f"validation_logits_{seed}.npy", allow_pickle=False) for seed in (42, 43, 44)]
        result = summarize(shared.label, shared.weight, logits, manifest["calibration"])
        if not np.isclose(result["metrics"]["macro_f1"], item["metrics"]["macro_f1"], atol=1e-10, rtol=0):
            raise ValueError("Macro-F1 local no reproduce el resultado remoto")
        models[name] = result
        rows.append(dict(model=name, macro_f1=result["metrics"]["macro_f1"],
            positive_precision=result["classes"]["positive"]["precision"],
            negative_precision=result["classes"]["negative"]["precision"],
            neutral_precision=result["classes"]["neutral"]["precision"],
            candidate_pair_coverage=result["candidate_pair_coverage"],
            evaluable_candidate_coverage=result["evaluable_candidate_coverage"],
            accepted_valence_pairs=result["accepted_valence_pairs"], abstained_pairs=result["abstained_pairs"]))
    destination = output(settings, study) / "training_development"
    destination.mkdir(exist_ok=False)
    pd.DataFrame(rows).to_csv(destination / "comparison.csv", index=False)
    context = json.loads((root / "common_context.json").read_text())
    atomic_json(destination / "comparison.json", dict(created_at=stamp(), models=models, common_context=context,
        completed_fits=expected_fits, production_enabled=False, independent_evaluation=False, reserved_test_opened=False,
        training_manifest_sha256=sha256(root / "manifest.json"),
        coverage_scope="conditional_on_extracted_shared_candidate_pairs; not end-to-end target coverage"))
    lines = [f"# Development comparison: {len(models)} models", "",
        "Reused, assisted validation; this is not an independent evaluation and does not enable production.", "",
        f"Shared complete context: {context['train_shared']}/{context['train_total']} training pairs and "
        f"{context['validation_shared']}/{context['validation_total']} validation pairs. {expected_fits} completed fits.", "",
        "| Model | Weighted macro-F1 | Accepted favorable precision | Accepted unfavorable precision | Candidate-pair coverage |",
        "|---|---:|---:|---:|---:|"]
    percent = lambda value: "No predictions" if value is None else f"{value:.2%}"
    for row in rows:
        lines.append(f"| {row['model']} | {row['macro_f1']:.4f} | {percent(row['positive_precision'])} | "
            f"{percent(row['negative_precision'])} | {percent(row['candidate_pair_coverage'])} |")
    lines += ["", "Macro-F1 averages positive/negative/neutral on all common pairs before abstention. "
        "Precision uses accepted predictions under the stored calibration. "
        "Candidate-pair coverage divides the weight of accepted positive/negative/neutral predictions by all common candidate-pair weight. "
        "It excludes extraction omissions and is not end-to-end target coverage or a historical score with another denominator.", "",
        "Temperature, thresholds, neutral precision, abstention counts, and per-seed metrics are in comparison.json. "
        "No model is automatically selected or promoted. Evaluation-sample predictions and confirmation of the new annotations "
        "remain separate from development diagnostics.", ""]
    (destination / "comparison.md").write_text("\n".join(lines))
    seal(destination, ["comparison.csv", "comparison.json", "comparison.md"], diagnostic_only=True)
    verify(study)
    return destination
