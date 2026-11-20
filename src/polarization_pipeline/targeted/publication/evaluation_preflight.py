"""Read-only evaluation prerequisites and observable reference exposure audit."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..annotations import text_key
from ..common import read_csv, sha256
from .state import verify, verify_seal


def exposure_audit(benchmark, cohorts):
    """Dates can prove a recorded exposure; missing dates never prove blindness."""
    rows = []
    for batch, sample, form in cohorts:
        if form.sample_id.duplicated().any() or set(form.sample_id) != set(sample.sample_id):
            raise ValueError("Identidades de revisión alteradas")
        reviewed = form.set_index("sample_id")
        for row in sample.to_dict("records"):
            decision = reviewed.loc[row["sample_id"]]
            rows.append(dict(comment_id=row["comment_id"], text_key=text_key(row["text"]), batch=batch,
                completed=str(decision["review_complete"]).lower() == "true",
                reviewer_id=decision["reviewer_id"], reviewed_at=decision["reviewed_at"]))
    overlap = []
    for item in benchmark.to_dict("records"):
        matches = [r for r in rows if r["comment_id"] == item["comment_id"] or r["text_key"] == text_key(item["text"])]
        if not matches:
            continue
        proven = False
        for previous in matches:
            if not previous["completed"] or not previous["reviewer_id"]:
                continue
            prior_date = pd.to_datetime(previous["reviewed_at"], utc=True, errors="coerce")
            own_date = pd.to_datetime(item.get("reviewed_at", ""), utc=True, errors="coerce")
            reviewer = item.get("reviewer_id", "")
            # If benchmark unreviewed, a prior exposure is known for the recorded reviewer,
            # but the identity of the future benchmark reviewer remains unknown.
            if reviewer and reviewer == previous["reviewer_id"] and pd.notna(prior_date) and pd.notna(own_date) and prior_date < own_date:
                proven = True
        overlap.append(dict(comment_id=item["comment_id"], cohorts=sorted({r["batch"] for r in matches}),
            exposure="recorded_prior_exposure" if proven else "potential_overlap_exposure_unknown"))
    return dict(overlapping_benchmark_comments=len(overlap),
        recorded_prior_exposure=sum(r["exposure"] == "recorded_prior_exposure" for r in overlap),
        potential_exposure_unknown=sum(r["exposure"] != "recorded_prior_exposure" for r in overlap),
        rows=overlap, limitation="Only recorded human review dates; unrecorded reading cannot be ruled out")


def sample_readiness(study, name):
    from .annotations import checked
    folder, sample, manifest, _ = checked(study, name)
    if sample.sample_id.duplicated().any() or sample.comment_id.duplicated().any():
        raise ValueError("Identidades duplicadas en muestra")
    proposals = json.loads((folder / "ai_proposals.json").read_text())
    if not set(proposals) <= set(sample.sample_id):
        raise ValueError("Propuestas ajenas a la muestra")
    form = read_csv(folder / "human_review.csv")
    if form.sample_id.duplicated().any() or set(form.sample_id) != set(sample.sample_id):
        raise ValueError("Identidades del formulario alteradas")
    original = sample.set_index("sample_id")
    if any(row.text != original.loc[row.sample_id, "text"] for row in form.itertuples()):
        raise ValueError("Texto del formulario alterado")
    if manifest["human_mode"] == "blind":
        complete = form.review_complete.str.lower().eq("true")
        if (form.loc[complete, "decision"].ne("blind").any() or form.loc[complete, "proposal_sha256"].ne("").any()):
            raise ValueError("Procedencia de revisión ciega incompatible")
    reviewed = form.review_complete.str.lower().eq("true")
    ready = bool(reviewed.all() and len(form))
    return sample, form, dict(comments=len(sample), proposals_complete=set(proposals)==set(sample.sample_id),
        human_review_complete=ready, reference_closed=(folder / "reference.json").exists(), mode=manifest["human_mode"])


def preflight(settings, plan, study, registry):
    verify(study)
    result = dict(study=study.name, read_only=True, production_enabled=False, reserved_test_opened=False,
        status="waiting_snapshot", requirements={}, ready_for_prediction=False,
        ready_for_provisional_benchmark=False, ready_for_final_benchmark=False)
    req = result["requirements"]
    for name in ("benchmark_initialized", "cohort_initialized", "cohort_proposals_complete",
                 "cohort_human_review_complete", "benchmark_proposals_complete", "benchmark_human_review_complete",
                 "benchmark_reference_closed", "prediction_input_prepared", "predictions_imported", "prediction_scope_complete"):
        req[name] = False
    req["training_imported"] = (study / "training").exists()
    if req["training_imported"]:
        verify_seal(study / "training")
        verify_seal(study / "training_input")
        comparison = json.loads((study / "training/comparison.json").read_text())
        if comparison["completed_fits"] != 12 or comparison["production_enabled"] is not False:
            raise ValueError("Entrenamiento incompatible")
    videos = read_csv(study / "videos.csv")
    counts = {"complete":0, "unavailable":0, "incomplete":0, "not_started":0}
    for video in videos.post_id:
        path = study / "raw_capture" / f"{video}.json"
        status = json.loads(path.read_text())["status"] if path.exists() else "not_started"
        if status not in counts:
            raise ValueError("Estado de captura desconocido")
        counts[status] += 1
    result["capture"] = counts
    req["capture_complete"] = counts["incomplete"] == counts["not_started"] == 0
    req["snapshot_frozen"] = (study / "freeze.json").exists()
    if not req["snapshot_frozen"]:
        result["next_command"] = "targeted publication collect" if not req["capture_complete"] else "targeted publication freeze"
        return result
    if not req["capture_complete"]:
        raise ValueError("Snapshot congelado con captura pendiente")
    verify(study, frozen=True)
    verify_seal(study, "capture_manifest.json")
    benchmark = read_csv(study / "benchmark.csv")
    if benchmark.comment_id.duplicated().any() or benchmark.sample_id.duplicated().any():
        raise ValueError("Benchmark con identidades duplicadas")
    probs = benchmark.sampling_probability.astype(float)
    if not np.isfinite(probs).all() or not probs.between(0,1,inclusive="right").all():
        raise ValueError("Probabilidades de muestreo inválidas")
    if len(benchmark) != sum(plan["benchmark_counts"]) or benchmark.bucket.value_counts().to_dict() != {
            name:n for name,n in zip(("izquierda","derecha","unknown","none"),plan["benchmark_counts"])}:
        raise ValueError("Cuotas del benchmark incompatibles")
    req["benchmark_initialized"] = (study / "annotations/benchmark").exists()
    folders = sorted((study / "annotations").glob("cohort_[0-9][0-9][0-9][0-9]"))
    req["cohort_initialized"] = bool(folders)
    samples, cohorts, readiness = [benchmark], [], {}
    for folder in folders:
        sample, form, info = sample_readiness(study, folder.name)
        samples.append(sample); cohorts.append((folder.name,sample,form)); readiness[folder.name]=info
        if info["human_review_complete"]:
            from .annotations import decisions
            decisions(study,folder.name,registry,"final")
    req["cohort_proposals_complete"] = bool(folders) and all(v["proposals_complete"] for v in readiness.values())
    req["cohort_human_review_complete"] = bool(folders) and all(v["human_review_complete"] for v in readiness.values())
    if cohorts and pd.concat([c[1] for c in cohorts]).comment_id.duplicated().any():
        raise ValueError("Comentarios repetidos entre lotes de cohorte")
    if req["benchmark_initialized"]:
        sample, form, info = sample_readiness(study,"benchmark")
        if not sample.sort_values("sample_id").reset_index(drop=True).equals(benchmark.sort_values("sample_id").reset_index(drop=True)):
            raise ValueError("La muestra de anotación difiere del benchmark congelado")
        readiness["benchmark"] = info
        req["benchmark_proposals_complete"] = info["proposals_complete"]
        req["benchmark_human_review_complete"] = info["human_review_complete"]
        req["benchmark_reference_closed"] = info["reference_closed"]
        if info["reference_closed"]:
            verify_seal(study / "annotations/benchmark", "reference.json")
        if info["human_review_complete"]:
            from .annotations import decisions
            decisions(study,"benchmark",registry,"final")
        benchmark = benchmark.merge(form[["sample_id","reviewer_id","reviewed_at"]],on="sample_id",validate="one_to_one")
    else:
        req["benchmark_proposals_complete"] = req["benchmark_human_review_complete"] = False
    result["samples"] = readiness
    result["exposure_audit"] = exposure_audit(benchmark,cohorts)
    result["ready_for_prediction"] = bool(req["training_imported"] and req["benchmark_initialized"] and req["cohort_initialized"])
    req["prediction_input_prepared"] = (study / "prediction_input.csv").exists() and (study / "prediction_scope.csv").exists()
    req["predictions_imported"] = (study / "predictions").exists()
    req["prediction_scope_complete"] = False
    if req["prediction_input_prepared"]:
        inputs = read_csv(study / "prediction_input.csv")
        if {"label","annotation_json","items","review_complete"} & set(inputs.columns):
            raise ValueError("La entrada de predicción contiene etiquetas nuevas")
        if inputs.duplicated(["comment_id","target_id"]).any():
            raise ValueError("Candidatos de predicción duplicados")
        scope = read_csv(study / "prediction_scope.csv")
        wanted = pd.concat(samples).drop_duplicates("comment_id")
        if scope.comment_id.duplicated().any():
            raise ValueError("Alcance de predicción duplicado")
        req["prediction_scope_complete"] = set(wanted.comment_id) <= set(scope.comment_id)
        expected_posts = wanted.set_index("comment_id").post_id
        selected = scope.loc[scope.comment_id.isin(expected_posts.index)]
        if any(r.post_id != expected_posts.loc[r.comment_id] for r in selected.itertuples()):
            raise ValueError("Videos de predicción incompatibles")
        payload = study / "kaggle/infer/payload/publication"
        if payload.exists():
            if {p.name for p in payload.iterdir()} != {"training", "prediction_input.csv", "prediction_scope.csv"}:
                raise ValueError("Payload de predicción fuera de la lista permitida")
            for name in ("prediction_input.csv", "prediction_scope.csv"):
                if sha256(payload / name) != sha256(study / name):
                    raise ValueError("El payload no corresponde a las entradas actuales")
            verify_seal(payload / "training")
    if req["predictions_imported"]:
        from .benchmark import MODEL_IDS
        manifest = verify_seal(study / "predictions")
        if not req["prediction_input_prepared"]:
            raise ValueError("Predicciones sin entrada local")
        if (not manifest.get("diagnostic_only") or manifest["prediction_input_sha256"] != sha256(study/"prediction_input.csv")
                or manifest["prediction_scope_sha256"] != sha256(study/"prediction_scope.csv")
                or manifest["training_sha256"] != sha256(study/"training/manifest.json")):
            raise ValueError("Procedencia de predicciones incompatible")
        expected = set(inputs[["comment_id","target_id","post_id"]].itertuples(index=False,name=None))
        for model in MODEL_IDS:
            predictions = read_csv(study / "predictions" / f"{model}.csv")
            keys=["comment_id","target_id","post_id"]
            if (predictions.duplicated(keys).any() or set(predictions.model_id)!={model}
                    or set(predictions[keys].itertuples(index=False,name=None)) != expected):
                raise ValueError("Predicciones incompletas o duplicadas")
    ready = req["predictions_imported"] and req["prediction_scope_complete"]
    result["ready_for_provisional_benchmark"] = bool(ready and req["benchmark_proposals_complete"] and (not folders or req["cohort_proposals_complete"]))
    result["ready_for_final_benchmark"] = bool(ready and req["benchmark_human_review_complete"] and (not folders or req["cohort_human_review_complete"]))
    result["status"] = "ready_for_final_benchmark" if result["ready_for_final_benchmark"] else "waiting_requirements"
    result["next_commands"] = ["targeted publication benchmark-init", "targeted publication next",
        "targeted publication predict", "targeted publication benchmark --stage provisional",
        "targeted publication benchmark --stage final"]
    result["commands_are_guidance_not_execution"] = True
    return result
