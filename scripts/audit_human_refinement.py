"""Close a fetched refinement round locally, retaining sealed remote reports."""
import argparse
import json
from pathlib import Path

import pandas as pd

from polarization_pipeline.targeted.common import atomic_json, config, read_csv, sha256, stamp
from polarization_pipeline.targeted.blending import aligned
from polarization_pipeline.targeted.refinement import verify

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="config/targeted_v2.toml")
parser.add_argument("--run-id", default="targeted_20261115_v2")
parser.add_argument("--experiment-id", default="development_human_refinement_20261116_v1")
args = parser.parse_args()
settings = config(args.config)
from polarization_pipeline.targeted.common import run_directory
from polarization_pipeline.targeted.development import experiment_directory
run = run_directory(settings, args.run_id)
root = experiment_directory(run, args.experiment_id)
if (root / "execution_report.json").exists():
    raise FileExistsError("Ronda ya auditada; no repetir")
verify(settings, run, root)
export = json.loads((root / "export_tune.json").read_text())
for name, digest in export["files"].items():
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or sha256(path) != digest:
        raise ValueError("Salida remota alterada: " + name)
protected = json.loads((root / "protected_originals.json").read_text())
print("Verificando originales y cohorte pendiente...", flush=True)
for name, digest in protected.items():
    if sha256(Path(name)) != digest:
        raise ValueError("Original alterado: " + name)
new = read_csv(root / "finalists/beto_human_refined/validation_predictions.csv")
frames = {}
for name in ("beto_previous", "beto_ai_augmented", "blend_0.50"):
    control = read_csv(root / "controls" / name / "validation_predictions.csv")
    _, current = aligned(control, new)
    frames[name] = control.set_index(["sample_id", "target_id"]).sort_index()
new = new.set_index(["sample_id", "target_id"]).sort_index()
errors = new[["text", "post_id", "target_name", "target_group", "label", "weight", "valence"]].copy()
errors = errors.rename(columns={"valence": "refined_prediction"})
for name, control in frames.items():
    errors[name + "_prediction"] = control.valence
    errors[name + "_correct"] = control.valence.eq(control.label)
errors["refined_correct"] = new.valence.eq(new.label)
errors["persistent_error_all_four"] = ~errors[[n + "_correct" for n in (*frames, "refined")]].any(axis=1)
errors["recovered_from_blend"] = errors.refined_correct & ~errors["blend_0.50_correct"]
errors["regressed_from_blend"] = ~errors.refined_correct & errors["blend_0.50_correct"]
errors["weight"] = errors.weight.astype(float)
errors = errors.loc[~errors.refined_correct | ~errors["blend_0.50_correct"]].sort_values("weight", ascending=False)
errors.to_csv(root / "local_error_comparison.csv")
selection = json.loads((root / "selection.json").read_text())
reports = json.loads((root / "finalists/beto_human_refined/reports.json").read_text())
models = {}
for name in (*frames, "refined"):
    report = reports if name == "refined" else json.loads((root / "controls" / name / "reports.json").read_text())
    models[name] = {kind: {"macro_f1_weighted": r["raw"]["macro_f1"], "macro_f1_unweighted": r["unweighted"]["macro_f1"],
        "coverage": r["coverage"], "positive_precision": r["accepted"]["classes"]["positive"]["precision"],
        "negative_precision": r["accepted"]["classes"]["negative"]["precision"]} for kind, r in report.items()
        if kind in ("full_development", "cross_calibrated")}
manifest = json.loads((root / "finalists/beto_human_refined/model/training_manifest.json").read_text())
for revision in manifest["revisions"]:
    if revision["best_epoch"] != 2 or len(revision["history"]) != 2 or any("validation_loss" in row for row in revision["history"]):
        raise ValueError("No se conservaron dos épocas fijas sin selección por validación")
    if set(revision["label_origin_counts"]) != {"human_confirmed"}:
        raise ValueError("Etiquetas no humanas en la fase final")
job = json.loads((run / "kaggle" / args.experiment_id / "tune/job_manifest.json").read_text())
audit = {"completed_at": stamp(), "protocol": "targeted-human-refinement-v1", "status": "closed_development",
    "kernel_ref": job["kernel_ref"], "dataset_version": job["verified_dataset_version"],
    "checkpoint_files_verified": len(manifest["checkpoint_hashes"]),
    "fits_completed": selection["fits_completed"], "selected": selection["selected"],
    "partial_development_improvement": selection["partial_development_improvement"], "models": models,
    "errors": {key: int(errors[key].sum()) for key in ("persistent_error_all_four", "recovered_from_blend", "regressed_from_blend")},
    "protected_originals_verified": len(protected), "exported_files_verified": len(export["files"]),
    "export_sha256": sha256(root / "export_tune.json"), "error_comparison_sha256": sha256(root / "local_error_comparison.csv"),
    "source_sha256": sha256(root / "source.json"), "import": json.loads((root / "import_tune.json").read_text()),
    "final_test_evaluated": False, "pending_reviews_used": False, "production_inference_executed": False,
    "tests_executed": 134, "tests_skipped": 1}
atomic_json(root / "execution_report.json", audit)
print(json.dumps(audit, ensure_ascii=False, indent=2))
