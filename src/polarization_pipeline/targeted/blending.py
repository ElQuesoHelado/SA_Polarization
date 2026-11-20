"""Bounded local development of probability mixtures; no model fits or final test."""
from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from .common import LABELS, atomic_json, read_csv, require_columns, sha256, stamp
from .development import experiment_directory
from .learning import calibrate, classification_metrics, evaluation_report, probabilities

PROTOCOL = "targeted-probability-blend-development-v1"
KEY = ["sample_id", "target_id"]
PROB = ["p_" + label for label in LABELS]


def validate_plan(plan):
    expected = dict(schema_version=1, protocol=PROTOCOL, parent_experiment_id="development_ai_augmentation_v1",
                    augmented_weights=[.25, .5, .75], maximum_new_candidates=3,
                    calibration_folds=5, seed=57, bootstrap_iterations=2000)
    if plan != expected:
        raise ValueError("Conservar las tres mezclas, cinco folds y presupuesto de desarrollo fijados")


def aligned(previous, augmented):
    """Refuse intersections, stale reference fields and non-probability inputs."""
    columns = KEY + PROB + ["split", "text", "comment_id", "post_id", "target_group", "label", "weight", "context_windowed"]
    for frame in (previous, augmented):
        require_columns(frame, columns)
        if not frame.split.eq("validation").all() or frame.duplicated(KEY).any() or frame.empty:
            raise ValueError("Solo pares únicos de validación; prueba y entrenamiento excluidos")
        if not frame.context_windowed.astype(str).str.lower().isin(["true", "false", "0", "1"]).all():
            raise ValueError("Estado de contexto inválido")
        p = frame[PROB].astype(float).to_numpy()
        if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any() or not np.allclose(p.sum(1), 1, atol=1e-6):
            raise ValueError("Probabilidades inválidas")
        w = frame.weight.astype(float).to_numpy()
        if not np.isfinite(w).all() or (w <= 0).any():
            raise ValueError("Pesos inválidos")
    left = previous.set_index(KEY).sort_index()
    right = augmented.set_index(KEY).sort_index()
    if not left.index.equals(right.index):
        raise ValueError("Comparar exactamente los mismos pares, sin intersecciones selectivas")
    for col in ("split", "text", "comment_id", "post_id", "target_group", "label"):
        if not left[col].equals(right[col]):
            raise ValueError("Identidad o referencia incompatible: " + col)
    if not np.allclose(left.weight.astype(float), right.weight.astype(float), rtol=1e-10, atol=0):
        raise ValueError("Pesos de referencia incompatibles")
    return left.reset_index(), right.reset_index()


def video_folds(frame, *, folds=5, seed=57):
    videos = sorted(set(frame.post_id), key=lambda value: hashlib.sha256(f"blend-calibration:{seed}:{value}".encode()).hexdigest())
    if len(videos) < folds:
        raise ValueError("Videos insuficientes para separar calibración")
    return frame.post_id.map({video: index % folds for index, video in enumerate(videos)}).to_numpy()


def apply_calibration(frame, p, calibration, valid):
    result = frame.drop(columns=[c for c in frame if c.startswith("seed_")], errors="ignore").copy()
    calibrated = probabilities(np.log(p.clip(1e-12)), calibration["temperature"])
    result["valence"] = np.array(LABELS)[calibrated.argmax(1)]
    result["confidence"] = calibrated.max(1)
    result["accepted"] = valid & np.array([confidence >= calibration["thresholds"][label]
        for label, confidence in zip(result.valence, result.confidence)])
    result["context_windowed"] = ~valid
    result["abstention_reason"] = np.where(~valid, "context_exceeds_validated_model_window",
        np.where(result.accepted, "", "confidence_below_threshold"))
    result[PROB] = calibrated
    return result


def cross_calibrate(frame, p, valid, *, precision, folds=5, seed=57):
    """Each video's labels are excluded from its own temperature/threshold fit."""
    fold = video_folds(frame, folds=folds, seed=seed)
    parts = []
    decisions = []
    labels = frame.label.to_numpy(); weights = frame.weight.astype(float).to_numpy()
    for index in range(folds):
        held = fold == index
        fit = ~held
        calibration = calibrate(np.log(p[fit].clip(1e-12)), labels[fit], weights[fit], precision, valid[fit])
        output = apply_calibration(frame.loc[held], p[held], calibration, valid[held])
        parts.append(output)
        decisions.append({"fold": index, "fit_videos": sorted(set(frame.loc[fit].post_id)),
                          "held_videos": sorted(set(frame.loc[held].post_id)), "calibration": calibration})
    result = pd.concat(parts).loc[frame.index]
    result["calibration_fold"] = fold
    return result, decisions


def development_report(settings, gold, predictions):
    report = evaluation_report(settings, gold, predictions, predictions)
    report["development_checks_passed"] = report.pop("status") == "passed"
    report["validation_comments"] = report.pop("test_comments")
    report["validation_pairs"] = report.pop("test_pairs")
    report.pop("thresholds_fixed_before_test")
    report["unweighted"] = classification_metrics(predictions.label, predictions.valence)
    report["final_test_evaluated"] = False
    return report


def prepare(settings, run, experiment_id, training_config):
    """Freeze inputs/decisions before computing any new candidate result."""
    plan = tomllib.loads(Path(training_config).read_text()); validate_plan(plan)
    root = experiment_directory(run, experiment_id)
    if root.exists():
        raise FileExistsError("Experimento ya preparado; conservarlo, no repetir la búsqueda")
    if (run / "model/test_opened.json").exists():
        raise ValueError("La prueba final debe permanecer reservada")
    parent = experiment_directory(run, plan["parent_experiment_id"])
    execution = json.loads((parent / "execution_report.json").read_text())
    export = json.loads((parent / "export_tune.json").read_text())
    source = json.loads((parent / "source.json").read_text())
    if (execution["export_sha256"] != sha256(parent / "export_tune.json")
        or execution["source_sha256"] != sha256(parent / "source.json")
        or execution["human_final_test_evaluated"] or execution["production_inference_executed"]
        or source["registry_sha256"] != sha256(settings["registry"]) or source["quality"] != settings["quality"]):
        raise ValueError("Padre, registro o criterios incompatibles")
    names = ["human_development.csv", "baseline/validation_predictions.csv", "baseline/validation_report.json",
             "baseline/manifest.json", "finalists/beto_ai_augmented/validation_predictions.csv",
             "finalists/beto_ai_augmented/model/calibration.json", "finalists/beto_ai_augmented/model/training_manifest.json"]
    inputs = {}
    for name in names:
        if sha256(parent / name) != export["files"][name]:
            raise ValueError("Artefacto padre alterado: " + name)
        inputs[str((parent / name).resolve())] = sha256(parent / name)
    gold = read_csv(parent / "human_development.csv")
    if not gold.split.isin(["train", "validation"]).all():
        raise ValueError("La fuente local debe contener únicamente desarrollo")
    # Guard final reference as opaque bytes; do not read/decode its annotations.
    manifest = json.loads((run / "annotations/manifest.json").read_text())
    if sha256(run / "annotations/gold.csv") != manifest["gold_sha256"]:
        raise ValueError("Referencia original alterada")
    protected_paths = [run / "annotations/gold.csv", run / "annotations/manifest.json", settings["registry"],
                       settings["_config_path"], settings["_root"] / "AGENTS.md", settings["_root"] / "docs/doc.tex"]
    protected_paths.extend(p for folder in (run / "cohorts", run / "model") for p in folder.rglob("*") if p.is_file())
    protected = {str(path.resolve()): sha256(path) for path in protected_paths}
    inputs.update({str((parent / name).resolve()): sha256(parent / name) for name in ("execution_report.json", "source.json", "export_tune.json")})
    inputs[str(Path(training_config).resolve())] = sha256(Path(training_config))
    root.mkdir(parents=True)
    atomic_json(root / "plan.json", {**plan, "created_at": stamp(), "quality": settings["quality"],
        "selection": "all full-development and cross-calibration checks, then weighted macro-F1, coverage, smaller augmented weight",
        "scope": "Validación reutilizada y asistida. Cross-calibración no deshace selección/early stopping previos ni constituye prueba independiente.",
        "no_pending_review_labels": True, "maximum_model_fits": 0, "production_enabled": False})
    atomic_json(root / "source.json", {"inputs": inputs, "protected": protected, "plan_sha256": sha256(root / "plan.json")})
    return root


def execute(settings, run, root):
    if (root / "execution_report.json").exists() or (root / "candidates").exists():
        raise FileExistsError("Conservar resultados existentes; no repetir candidatos")
    source = json.loads((root / "source.json").read_text()); plan = json.loads((root / "plan.json").read_text())
    if sha256(root / "plan.json") != source["plan_sha256"] or settings["quality"] != plan["quality"]:
        raise ValueError("Plan o criterios alterados")
    def check_inputs():
        if (run / "model/test_opened.json").exists():
            raise ValueError("La prueba final debe permanecer reservada")
        for name, digest in (source["inputs"] | source["protected"]).items():
            if sha256(Path(name)) != digest:
                raise ValueError("Entrada o archivo protegido alterado: " + name)
    check_inputs()
    parent = experiment_directory(run, plan["parent_experiment_id"])
    gold = read_csv(parent / "human_development.csv")
    if not gold.split.isin(["train", "validation"]).all():
        raise ValueError("Solo desarrollo")
    gold = gold.loc[gold.split.eq("validation")].copy()
    old, new = aligned(read_csv(parent / "baseline/validation_predictions.csv"),
                       read_csv(parent / "finalists/beto_ai_augmented/validation_predictions.csv"))
    from .diagnostics import validation_diagnostics
    from .registry import Matcher, load_registry
    registry = load_registry(settings["registry"]); targets = {x["target_id"]: x for x in registry["targets"]}
    matcher = Matcher(registry)
    gold["items"] = gold.annotation_json.map(json.loads); gold["weight"] = 1 / gold.sampling_probability.astype(float)
    # Validate predictions against genuine human development before any mixture.
    for name in ("baseline/validation_predictions.csv", "finalists/beto_ai_augmented/validation_predictions.csv"):
        validation_diagnostics(gold, parent / name, targets, matcher)
    oldp = old[PROB].astype(float).to_numpy(); newp = new[PROB].astype(float).to_numpy()
    def complete(frame):
        return frame.context_windowed.astype(str).str.lower().isin(["false", "0"]).to_numpy()
    results = []; predictions = {}
    for alpha in [0., *plan["augmented_weights"], 1.]:
        name = f"blend_{alpha:.2f}"; folder = root / "candidates" / name; folder.mkdir(parents=True)
        p = (1 - alpha) * oldp + alpha * newp
        valid = complete(old) if alpha == 0 else complete(new) if alpha == 1 else complete(old) & complete(new)
        cross, folds = cross_calibrate(old, p, valid, precision=settings["quality"]["valence_precision"],
                                      folds=plan["calibration_folds"], seed=plan["seed"])
        cross.to_csv(folder / "cross_calibrated_predictions.csv", index=False)
        atomic_json(folder / "calibration_folds.json", folds)
        calibration = calibrate(np.log(p.clip(1e-12)), old.label.to_numpy(), old.weight.astype(float).to_numpy(),
                                settings["quality"]["valence_precision"], valid)
        full = apply_calibration(old, p, calibration, valid)
        full.to_csv(folder / "validation_predictions.csv", index=False)
        atomic_json(folder / "calibration.json", calibration)
        reports = {"full_development": development_report(settings, gold, full),
                   "cross_calibrated": development_report(settings, gold, cross)}
        slices, _, metrics = validation_diagnostics(gold, folder / "cross_calibrated_predictions.csv", targets, matcher)
        pd.DataFrame(slices).to_csv(folder / "coverage_by_group.csv", index=False)
        reports["cross_calibrated_slices"] = {k: v for k, v in metrics.items() if k != "performance_slices"}
        atomic_json(folder / "reports.json", reports)
        full_report = reports["full_development"]; cross_report = reports["cross_calibrated"]
        results.append({"id": name, "augmented_weight": alpha, "new_candidate": alpha not in (0, 1),
            "macro_f1": full_report["raw"]["macro_f1"], "macro_f1_unweighted": full_report["unweighted"]["macro_f1"],
            "coverage_full": full_report["coverage"], "coverage_cross_calibrated": cross_report["coverage"],
            "cross_positive_precision": cross_report["accepted"]["classes"]["positive"]["precision"],
            "cross_negative_precision": cross_report["accepted"]["classes"]["negative"]["precision"],
            "full_development_checks": full_report["checks"], "cross_calibrated_checks": cross_report["checks"],
            "eligible_in_development": full_report["development_checks_passed"] and cross_report["development_checks_passed"]})
        predictions[name] = cross
    candidates = sorted([x for x in results if x["new_candidate"]], key=lambda x:
        (-int(x["eligible_in_development"]), -x["macro_f1"], -x["coverage_cross_calibrated"], x["augmented_weight"]))
    best = candidates[0]
    selected = best["id"] if best["eligible_in_development"] else None
    from .ai_augmentation import paired_video_bootstrap
    bootstrap = paired_video_bootstrap(gold, predictions["blend_0.00"], predictions[best["id"]], targets,
                                      draws=plan["bootstrap_iterations"], seed=plan["seed"])
    bootstrap["limitation"] += " La asignación de folds queda fija y no se recalibra en cada remuestreo."
    atomic_json(root / "paired_bootstrap.json", bootstrap)
    atomic_json(root / "selection.json", {"selected": selected, "best_development_candidate": best["id"],
        "candidates": results, "new_candidates_evaluated": len(candidates), "model_fits": 0,
        "final_test_evaluated": False, "production_enabled": False, "pending_reviews_used": False, "scope": plan["scope"]})
    atomic_json(root / "ensemble_spec.json", {"augmented_weight": best["augmented_weight"],
        "calibration": json.loads((root / "candidates" / best["id"] / "calibration.json").read_text()),
        "parent": plan["parent_experiment_id"], "sources": source["inputs"], "development_only": True,
        "production_enabled": False, "candidate_meets_development_checks": bool(selected)})
    lines = ["# Combinación local de BETO: desarrollo", "", plan["scope"], "",
        "Tres mezclas prefijadas; extremos como controles. Cero ajustes de modelos, sin usar nuevas etiquetas ni las revisiones pendientes.",
        "Cada video se excluye de la calibración de sus propias predicciones. Los modelos ya utilizaron esta validación en rondas anteriores.", "",
        "| Peso ampliado | F1 ponderado | F1 sin pesos | Cobertura calibración completa | Cobertura calibración separada | P+ separada | P− separada |",
        "|---:|---:|---:|---:|---:|---:|---:|"]
    for x in results:
        lines.append(f"| {x['augmented_weight']:.2f} | {x['macro_f1']:.4f} | {x['macro_f1_unweighted']:.4f} | {x['coverage_full']:.2%} | {x['coverage_cross_calibrated']:.2%} | {x['cross_positive_precision']:.2%} | {x['cross_negative_precision']:.2%} |")
    lines += ["", f"Mejor mezcla en desarrollo: {best['id']}. Seleccionado por todos los criterios: {selected}.",
        "Pesos/criterios/registro intactos; ninguna mezcla se promueve al modelo canónico. No hay AP nueva ni evidencia independiente de polarización.", ""]
    (root / "comparison.md").write_text("\n".join(lines))
    check_inputs()
    artifacts = {str(path.relative_to(root)): sha256(path) for path in root.rglob("*") if path.is_file()}
    atomic_json(root / "execution_report.json", {"status": "complete_development_only", "completed_at": stamp(),
        "artifacts": artifacts, "protected_files_verified": len(source["protected"]), "inputs_verified": len(source["inputs"]),
        "model_fits": 0, "new_candidates": len(candidates), "selected": selected, "final_test_evaluated": False,
        "pending_reviews_used": False, "production_inference_executed": False})
    return root
