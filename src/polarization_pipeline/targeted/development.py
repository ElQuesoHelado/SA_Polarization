"""Isolated development diagnostics and bounded model selection; never opens final test."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from .common import LABELS, atomic_json, read_csv, sha256, stamp
from .registry import Matcher, load_registry, registry_fingerprint
from .learning import (calibrate, classification_metrics, complete_context, encoding,
                       ensemble_predict, evaluation_report, predict_logits, probabilities, _gpu)


def experiment_directory(run: Path, experiment_id: str) -> Path:
    if not experiment_id or not re.fullmatch(r"[A-Za-z0-9_-]+", experiment_id):
        raise ValueError("experiment-id inválido")
    return run / "experiments" / experiment_id


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode()


def development_data(settings: dict, run: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Verify the reference, then discard final rows before extracting/scoring targets."""
    from .assisted import verify_completed
    from .annotations import check_development_extraction
    manifest = json.loads((run / "annotations/manifest.json").read_text())
    if manifest.get("annotation_protocol") != "ai_assisted_single_human_v1" or manifest.get("status") != "human_reviewed_assisted":
        raise ValueError("Desarrollo requiere la referencia asistida cerrada")
    verify_completed(settings, run)
    if sha256(run / "annotations/gold.csv") != manifest["gold_sha256"] or registry_fingerprint(settings["registry"]) != manifest["registry_sha256"]:
        raise ValueError("Referencia o registro modificados")
    if (run / "corpus_main.csv").exists() and manifest.get("corpus_main_sha256") != sha256(run / "corpus_main.csv"):
        raise ValueError("Corpus modificado")
    gold = read_csv(run / "annotations/gold.csv")
    gold = gold.loc[gold.split.isin(["train", "validation"])].copy()
    if gold.empty or gold.groupby("post_id").split.nunique().gt(1).any():
        raise ValueError("Desarrollo vacío o con videos compartidos")
    check_development_extraction(settings, gold)
    matcher = Matcher(load_registry(settings["registry"], frozen=True))
    rows = []
    for row in gold.to_dict("records"):
        annotations = {item["target_id"]: item for item in json.loads(row["annotation_json"])}
        for match in matcher.find(row["text"], row["comment_published_at"]):
            rows.append({**row, **match, "label": annotations.get(match["target_id"], {}).get("valence", "not_evaluable"),
                         "weight": 1 / float(row["sampling_probability"])})
    pairs = pd.DataFrame(rows)
    if pairs.empty or not pairs.split.eq("validation").any():
        raise ValueError("Sin pares de desarrollo")
    return gold, pairs


def freeze_experiment(settings: dict, run: Path, experiment_id: str, training_config: Path) -> Path:
    """Resolve model revisions once, before a job is published."""
    from .ai_augmentation import PROTOCOL as AI_PROTOCOL, freeze as freeze_ai
    from .refinement import PROTOCOL as REFINEMENT_PROTOCOL, freeze as freeze_refinement
    if tomllib.loads(training_config.read_text()).get("protocol") == REFINEMENT_PROTOCOL:
        return freeze_refinement(settings, run, experiment_id, training_config)
    if tomllib.loads(training_config.read_text()).get("protocol") == AI_PROTOCOL:
        return freeze_ai(settings, run, experiment_id, training_config)
    root = experiment_directory(run, experiment_id)
    if root.exists():
        plan = json.loads((root / "plan.json").read_text())
        if plan["training_config_sha256"] != sha256(training_config):
            raise ValueError("Configuración distinta del experimento congelado")
        development_data(settings, run)
        verify_source(settings, run, root)
        return root
    gold, pairs = development_data(settings, run)
    with training_config.open("rb") as handle:
        plan = tomllib.load(handle)
    from .targetaware import PROTOCOL, validate_plan, parent_reference
    target_aware = plan.get("protocol") == PROTOCOL
    if target_aware:
        validate_plan(plan)
    elif (plan.get("protocol") != "targeted-development-comparison-v1" or plan.get("maximum_fits") != 12 or plan.get("final_seeds") != [42, 43, 44]
            or plan.get("screening_seed") != 42 or plan.get("effective_batch_size") != 16
            or plan.get("learning_rates") != [1e-5, 2e-5]
            or plan.get("objectives") != ["class_balanced", "sampling_weighted"]
            or plan.get("maximum_epochs") != 8 or plan.get("patience") != 2
            or [m["id"] for m in plan.get("models", [])] != ["robertuito", "beto"]):
        raise ValueError("La búsqueda debe conservar el presupuesto y la cuadrícula autorizados")
    import urllib.request
    for model in plan["models"]:
        if model["revision"] == "resolve_once":
            url = "https://huggingface.co/api/models/" + model["model"]
            with urllib.request.urlopen(url, timeout=60) as response:
                model["revision"] = json.load(response)["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", model["revision"]):
            raise ValueError("Se requiere una revisión inmutable del modelo")
    manifest = json.loads((run / "annotations/manifest.json").read_text())
    source = {"study_gold_sha256": manifest.get("study_gold_sha256", manifest["gold_sha256"]),
              "registry_sha256": sha256(settings["registry"]), "development_gold_sha256": hashlib.sha256(csv_bytes(gold)).hexdigest(),
              "development_pairs_sha256": hashlib.sha256(csv_bytes(pairs)).hexdigest(),
              "baseline_training_manifest_sha256": sha256(run / "model/training_manifest.json"),
              "comments_by_split": gold.split.value_counts().to_dict(), "quality": settings["quality"],
              "annotation_protocol": manifest["annotation_protocol"], "annotation_limitation": manifest["annotation_limitation"],
              "sampling_probability_scope": manifest.get("sampling_probability_scope"), "created_at": stamp()}
    references = {}
    if target_aware:
        source["parent_reference"], references = parent_reference(settings, run, plan)
    plan.update(training_config_sha256=sha256(training_config), experiment_id=experiment_id, frozen_at=stamp())
    root.mkdir(parents=True, exist_ok=False)
    atomic_json(root / "plan.json", plan)
    source["plan_sha256"] = sha256(root / "plan.json")
    atomic_json(root / "source.json", source)
    for name, path in references.items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    return root


def verify_source(settings: dict, run: Path, root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    from .refinement import PROTOCOL as REFINEMENT_PROTOCOL, verify as verify_refinement
    if json.loads((root / "plan.json").read_text()).get("protocol") == REFINEMENT_PROTOCOL:
        return verify_refinement(settings, run, root)
    from .ai_augmentation import PROTOCOL as AI_PROTOCOL, verify as verify_ai
    if json.loads((root / "plan.json").read_text()).get("protocol") == AI_PROTOCOL:
        return verify_ai(settings, run, root)
    gold, pairs = development_data(settings, run)
    source = json.loads((root / "source.json").read_text())
    manifest = json.loads((run / "annotations/manifest.json").read_text())
    if (source["plan_sha256"] != sha256(root / "plan.json")
            or source["study_gold_sha256"] != manifest.get("study_gold_sha256", manifest["gold_sha256"])
            or source["registry_sha256"] != sha256(settings["registry"]) or source["quality"] != settings["quality"]
            or source["development_gold_sha256"] != hashlib.sha256(csv_bytes(gold)).hexdigest()
            or source["development_pairs_sha256"] != hashlib.sha256(csv_bytes(pairs)).hexdigest()):
        raise ValueError("El experimento no corresponde al desarrollo congelado")
    for name, digest in source.get("parent_reference", {}).get("files", {}).items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path) != digest:
            raise ValueError("Referencia padre alterada")
    return gold, pairs


def maximum_length(model_config, tokenizer, requested: int) -> int:
    capacity = int(model_config.max_position_embeddings)
    if model_config.model_type == "roberta":
        capacity -= int(model_config.pad_token_id) + 1
    maximum = min(requested, capacity, int(tokenizer.model_max_length))
    if maximum < 16:
        raise ValueError("Capacidad de contexto inválida")
    return maximum


def loss_weights(training: pd.DataFrame, objective: str) -> np.ndarray:
    if objective == "ai_augmented":
        if not set(training.label_origin) <= {"human_confirmed", "ai_auxiliary"}:
            raise ValueError("Origen de etiquetas inválido")
        counts = training.loc[training.label_origin.eq("human_confirmed")].label.value_counts()
        if not set(training.label) <= set(counts.index):
            raise ValueError("Clases IA sin referencia humana")
        values = training.label.map(lambda label: 1 / np.sqrt(counts[label])).to_numpy()
        values = values * np.where(training.label_origin.eq("ai_auxiliary"), .25, 1.0)
    elif objective == "class_balanced":
        counts = training.label.value_counts()
        values = training.label.map(lambda label: 1 / np.sqrt(counts[label])).to_numpy()
    elif objective == "sampling_weighted":
        values = training.weight.astype(float).to_numpy()
    else:
        raise ValueError("Objetivo de entrenamiento desconocido")
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("Pesos de entrenamiento inválidos")
    return values / values.mean()


def rank_report(item: dict) -> tuple:
    report = item["report"]
    return (-int(report["ready_for_reserved_test"]), -report["raw"]["macro_f1"],
            -report["coverage"], report["weighted_loss"], item["id"])


def write_diagnostics(settings: dict, gold: pd.DataFrame, predictions: pd.DataFrame, folder: Path,
                      calibration: dict, maximum: int, weighted_loss: float) -> dict:
    if not gold.split.eq("validation").all() or not predictions.split.eq("validation").all():
        raise ValueError("El diagnóstico admite exclusivamente validación")
    folder.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(folder / "validation_predictions.csv", index=False)
    report = evaluation_report(settings, gold, predictions, predictions)
    ready = report.pop("status") == "passed"
    report["validation_comments"] = report.pop("test_comments")
    report["validation_pairs"] = report.pop("test_pairs")
    report.pop("thresholds_fixed_before_test")
    report.update(status="development_ready" if ready else "development_not_ready", ready_for_reserved_test=ready,
                  final_test_evaluated=False, scope="Desarrollo reutilizado y asistido; selección y calibración sobre validación, sin evaluación final.",
                  weighted_loss=float(weighted_loss), calibration=calibration, maximum_tokens=maximum,
                  unweighted=classification_metrics(predictions.label, predictions.valence),
                  context_incomplete_pairs=int(predictions.context_windowed.sum()))
    confusion = predictions.groupby(["label", "valence"], sort=True).agg(count=("weight", "size"), weighted_count=("weight", lambda s: s.astype(float).sum())).reset_index()
    confusion.to_csv(folder / "confusion.csv", index=False)
    curve = []
    reasons = {}
    for label in LABELS:
        for threshold in np.round(np.arange(0.5, 1, 0.05), 2):
            selected = predictions.loc[predictions.valence.eq(label) & predictions.confidence.ge(threshold) & ~predictions.context_windowed]
            correct = selected.label.eq(label).to_numpy()
            weight = selected.weight.astype(float).to_numpy()
            curve.append({"label": label, "threshold": threshold, "pairs": len(selected),
                          "accepted_weight": float(weight.sum()),
                          "pair_coverage": float(weight.sum() / predictions.weight.astype(float).sum()),
                          "weighted_precision": float(np.average(correct, weights=weight)) if len(selected) else 0.0,
                          "minimum_support_met": len(selected) >= 10})
        eligible = [row for row in curve if row["label"] == label and row["minimum_support_met"]]
        reasons[label] = "enabled" if calibration["thresholds"][label] <= 1 else "insufficient_support" if not eligible else "precision_below_target"
    pd.DataFrame(curve).to_csv(folder / "precision_coverage_curve.csv", index=False)
    report["calibration_diagnosis"] = reasons
    from .targetaware import diagnostic_slices
    report.update(diagnostic_slices(gold, predictions))
    atomic_json(folder / "validation_report.json", report)
    return report


def annotate_lengths(predictions: pd.DataFrame, folder: Path, maximum: int) -> pd.DataFrame:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(folder, use_fast=False)
    result = predictions.copy()
    result["input_tokens"] = [len(tokenizer.encode(row.text, add_special_tokens=False))
                              + len(tokenizer.encode(row.target_name, add_special_tokens=False))
                              + tokenizer.num_special_tokens_to_add(pair=True) for row in result.itertuples(index=False)]
    result["maximum_tokens"] = maximum
    from .targetaware import representation, input_lengths
    if representation(tokenizer) != "pair_cls":
        result["input_tokens"] = input_lengths(tokenizer, predictions)
    return result


def validate(settings: dict, run: Path, experiment_id: str) -> None:
    root = experiment_directory(run, experiment_id)
    gold, pairs = verify_source(settings, run, root)
    source = json.loads((root / "source.json").read_text())
    if sha256(run / "model/training_manifest.json") != source["baseline_training_manifest_sha256"]:
        raise ValueError("Modelo de referencia distinto del congelado")
    if (root / "baseline").exists():
        raise FileExistsError("El diagnóstico de referencia ya existe")
    selected = pairs.loc[pairs.split.eq("validation")].copy()
    predictions = ensemble_predict(settings, run, selected)
    manifest = json.loads((run / "model/training_manifest.json").read_text())
    maximum = manifest["revisions"][0]["maximum_tokens"]
    predictions = annotate_lengths(predictions, run / "model" / str(manifest["revisions"][0]["seed"]), maximum)
    calibration = json.loads((run / "model/calibration.json").read_text())
    p = predictions[["p_" + label for label in LABELS]].to_numpy()
    y = np.array([LABELS.index(label) for label in predictions.label])
    loss = np.average(-np.log(p[np.arange(len(y)), y].clip(1e-12)), weights=predictions.weight.astype(float))
    report = write_diagnostics(settings, gold.loc[gold.split.eq("validation")], predictions, root / "baseline", calibration, maximum, loss)
    atomic_json(root / "baseline/manifest.json", {"created_at": stamp(), "baseline_training_manifest_sha256": source["baseline_training_manifest_sha256"],
                                                "report_sha256": sha256(root / "baseline/validation_report.json"), "final_test_evaluated": False})
    print("BASELINE_VALIDATION_COMPLETE", report["raw"]["macro_f1"], report["calibration_diagnosis"], flush=True)


def backward_microbatches(torch, model, tokenizer, logical: list[dict], maximum: int,
                         physical_size: int, encode=encoding) -> None:
    device = next(model.parameters()).device
    for offset in range(0, len(logical), physical_size):
        batch = logical[offset:offset + physical_size]
        inputs = {key: value.to(device) for key, value in encode(tokenizer, batch, maximum).items()}
        labels = torch.tensor([LABELS.index(row["label"]) for row in batch], device=device)
        weights = torch.tensor([row["loss_weight"] for row in batch], dtype=next(model.parameters()).dtype, device=device)
        loss = (torch.nn.functional.cross_entropy(model(**inputs).logits, labels, reduction="none") * weights).sum() / len(logical)
        loss.backward()


def verify_accumulation() -> None:
    """Numerical self-check in the torch environment, before any real training."""
    from types import SimpleNamespace
    import torch
    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.layer = torch.nn.Linear(2, len(LABELS), dtype=torch.float64)
        def forward(self, features):
            return SimpleNamespace(logits=self.layer(features))
    def encode(tokenizer, batch, maximum):
        return {"features": torch.tensor([row["features"] for row in batch], dtype=torch.float64)}
    torch.manual_seed(0)
    model = Model()
    rows = [{"features": [i / 10, 1.0], "label": LABELS[i % len(LABELS)], "loss_weight": 0.5 + i / 10} for i in range(10)]
    backward_microbatches(torch, model, None, rows, 0, 10, encode)
    expected = [p.grad.clone() for p in model.parameters()]
    for size in (4, 3, 1):
        model.zero_grad()
        backward_microbatches(torch, model, None, rows, 0, size, encode)
        if not all(torch.allclose(p.grad, value, atol=1e-12, rtol=1e-10) for p, value in zip(model.parameters(), expected)):
            raise RuntimeError("Acumulación de gradientes inconsistente")
    print("GRADIENT_ACCUMULATION_VERIFIED", flush=True)


def fit_seed(settings: dict, training: pd.DataFrame, validation: pd.DataFrame, folder: Path,
             model_spec: dict, trial: dict, plan: dict, seed: int, *, initial_checkpoint: Path | None = None) -> tuple[dict, np.ndarray]:
    import random
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    torch = _gpu()
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    from .targetaware import initialize_model, load_classifier
    fixed = bool(plan.get("fixed_epochs", False))
    if initial_checkpoint is not None:
        from .refinement import initialize_checkpoint, validate_human_training
        validate_human_training(training)
        if not fixed or plan["maximum_epochs"] != 2 or trial["learning_rate"] != 2e-6 or trial["objective"] != "class_balanced":
            raise ValueError("Refinamiento requiere dos épocas fijas y receta humana congelada")
        model, tokenizer = initialize_checkpoint(initial_checkpoint)
    else:
        if fixed:
            raise ValueError("Épocas fijas reservadas al refinamiento desde checkpoint")
        model, tokenizer = initialize_model(model_spec)
    model = model.cuda()
    maximum = maximum_length(model.config, tokenizer, model_spec["maximum_tokens"])
    fit = training.loc[complete_context(tokenizer, training, maximum)].copy()
    if not set(LABELS[:3]) <= set(fit.label):
        raise ValueError("Faltan clases con contexto completo")
    fit["loss_weight"] = loss_weights(fit, trial["objective"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=trial["learning_rate"], weight_decay=plan["weight_decay"])
    destination = folder / str(seed); destination.mkdir(parents=True, exist_ok=False)
    best, patience, best_epoch = float("inf"), 0, 0
    history = []
    y = np.array([LABELS.index(label) for label in validation.label])
    for epoch in range(plan["maximum_epochs"]):
        model.train()
        records = fit.sample(frac=1, random_state=seed + epoch).to_dict("records")
        logical_size = plan["effective_batch_size"]
        physical_size = model_spec["physical_batch_size"]
        for start in range(0, len(records), logical_size):
            logical = records[start:start + logical_size]
            optimizer.zero_grad()
            backward_microbatches(torch, model, tokenizer, logical, maximum, physical_size)
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["gradient_clip"])
            optimizer.step()
        if fixed:
            # No validation labels/predictions choose epochs in this protocol.
            history.append({"epoch": epoch + 1, "checkpoint_policy": "fixed_final_epoch"})
            if epoch + 1 == plan["maximum_epochs"]:
                model.save_pretrained(destination, safe_serialization=True); tokenizer.save_pretrained(destination)
                best_epoch = epoch + 1
            print(f"REFINEMENT seed={seed} epoch={epoch + 1} fixed_final_epoch=2", flush=True)
            continue
        logits = predict_logits(model, tokenizer, validation, maximum)
        probability = probabilities(logits)
        loss_value = float(np.average(-np.log(probability[np.arange(len(y)), y].clip(1e-12)), weights=validation.weight.astype(float)))
        history.append({"epoch": epoch + 1, "validation_loss": loss_value})
        print(f"TRIAL {trial['id']} seed={seed} epoch={epoch + 1} loss={loss_value:.6f}", flush=True)
        if loss_value < best:
            best, patience, best_epoch = loss_value, 0, epoch + 1
            model.save_pretrained(destination, safe_serialization=True); tokenizer.save_pretrained(destination)
        else:
            patience += 1
            if patience >= plan["patience"]:
                break
    del model, optimizer
    torch.cuda.empty_cache()
    selected = load_classifier(destination).cuda()
    logits = predict_logits(selected, tokenizer, validation, maximum)
    del selected
    torch.cuda.empty_cache()
    np.save(folder / f"validation_logits_{seed}.npy", logits, allow_pickle=False)
    return {"seed": seed, "base_revision": model_spec["revision"], "maximum_tokens": maximum, "history": history,
            "best_epoch": best_epoch, "training_pairs": len(fit), "excluded_incomplete_context": len(training) - len(fit),
            "class_counts": fit.label.value_counts().to_dict(),
            "label_origin_counts": fit.label_origin.value_counts().to_dict() if "label_origin" in fit else None,
            "loss_policy": "human_class_counts_inverse_sqrt; ai_factor=0.25; normalize_mean=1" if trial["objective"] == "ai_augmented" else trial["objective"],
            "representation": model_spec.get("representation", "pair_cls")}, logits


def finish_model(settings: dict, run: Path, source: dict, root: Path, model_spec: dict,
                 trial: dict, validation: pd.DataFrame, revisions: list[dict], logits: list[np.ndarray], *, gold_override=None) -> dict:
    from transformers import AutoTokenizer
    folder = root / "model"
    first = revisions[0]
    tokenizer = AutoTokenizer.from_pretrained(folder / str(first["seed"]), use_fast=False)
    mean = np.mean([probabilities(values) for values in logits], axis=0)
    calibration = calibrate(np.log(mean.clip(1e-12)), validation.label.to_numpy(), validation.weight.astype(float).to_numpy(),
                            settings["quality"]["valence_precision"], complete_context(tokenizer, validation, first["maximum_tokens"]))
    atomic_json(folder / "calibration.json", calibration)
    manifest = {"created_at": stamp(), "status": "development_only", "base_model": model_spec["model"], "revisions": revisions,
                "registry_sha256": source["registry_sha256"], "gold_sha256": source["study_gold_sha256"],
                "development_gold_sha256": source["development_gold_sha256"], "annotation_protocol": source["annotation_protocol"],
                "annotation_limitation": source["annotation_limitation"], "sampling_probability_scope": source.get("sampling_probability_scope"),
                "method_version": settings["method_version"], "trial": trial,
                "checkpoint_hashes": {str(p.relative_to(folder)): sha256(p) for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "training_manifest.json"}}
    atomic_json(folder / "training_manifest.json", manifest)
    predictions = ensemble_predict(settings, run, validation, model_folder=folder)
    predictions = annotate_lengths(predictions, folder / str(first["seed"]), first["maximum_tokens"])
    y = np.array([LABELS.index(label) for label in validation.label])
    loss = np.average(-np.log(mean[np.arange(len(y)), y].clip(1e-12)), weights=validation.weight.astype(float))
    gold = gold_override
    if gold is None:
        gold, _ = development_data(settings, run)
    report = write_diagnostics(settings, gold.loc[gold.split.eq("validation")], predictions, root, calibration, first["maximum_tokens"], loss)
    atomic_json(root / "trial.json", {"id": trial["id"], "model": model_spec, "training": trial, "seeds": [x["seed"] for x in revisions],
                                     "model_manifest_sha256": sha256(folder / "training_manifest.json"), "report_sha256": sha256(root / "validation_report.json")})
    return report


def tune(settings: dict, run: Path, experiment_id: str) -> None:
    root = experiment_directory(run, experiment_id)
    gold, pairs = verify_source(settings, run, root)
    plan = json.loads((root / "plan.json").read_text()); source = json.loads((root / "source.json").read_text())
    from .refinement import PROTOCOL as REFINEMENT_PROTOCOL, tune as tune_refinement
    if plan.get("protocol") == REFINEMENT_PROTOCOL:
        tune_refinement(settings, run, root, gold, pairs, plan, source)
        return
    from .ai_augmentation import PROTOCOL as AI_PROTOCOL, tune as tune_ai
    if plan.get("protocol") == AI_PROTOCOL:
        tune_ai(settings, run, root, gold, pairs, plan, source)
        return
    from .targetaware import PROTOCOL, tune_targetaware
    if plan.get("protocol") == PROTOCOL:
        tune_targetaware(settings, run, root, gold, pairs, plan, source)
        return
    if not (root / "baseline/manifest.json").exists() or (root / "trials").exists():
        raise ValueError("Primero importar diagnóstico; conservar búsquedas ya iniciadas")
    verify_accumulation()
    training = pairs.loc[pairs.split.eq("train")].copy(); validation = pairs.loc[pairs.split.eq("validation")].copy()
    finalists = []
    fits = 0
    for model_spec in plan["models"]:
        trials = []
        for rate in plan["learning_rates"]:
            for objective in plan["objectives"]:
                trial = {"id": f"{model_spec['id']}_{rate:g}_{objective}", "learning_rate": rate, "objective": objective}
                path = root / "trials" / trial["id"]
                revision, logits = fit_seed(settings, training, validation, path / "model", model_spec, trial, plan, plan["screening_seed"])
                fits += 1
                report = finish_model(settings, run, source, path, model_spec, trial, validation, [revision], [logits])
                trials.append({"id": trial["id"], "report": report, "trial": trial, "path": path, "revision": revision, "logits": logits})
                atomic_json(root / "progress.json", {"fits_completed": fits, "last_trial": trial["id"], "final_test_evaluated": False})
        best = sorted(trials, key=rank_report)[0]
        path = root / "finalists" / model_spec["id"]
        (path / "model").mkdir(parents=True, exist_ok=False)
        shutil.copytree(best["path"] / "model" / "42", path / "model/42")
        np.save(path / "model/validation_logits_42.npy", best["logits"], allow_pickle=False)
        revisions, logits = [best["revision"]], [best["logits"]]
        for seed in plan["final_seeds"][1:]:
            revision, values = fit_seed(settings, training, validation, path / "model", model_spec, best["trial"], plan, seed)
            fits += 1
            revisions.append(revision); logits.append(values)
            atomic_json(root / "progress.json", {"fits_completed": fits, "last_trial": best["id"], "last_seed": seed, "final_test_evaluated": False})
        report = finish_model(settings, run, source, path, model_spec, best["trial"], validation, revisions, logits)
        finalists.append({"id": model_spec["id"], "report": report, "trial_id": best["id"], "model_path": str(path.relative_to(root) / "model")})
    assert fits <= plan["maximum_fits"]
    eligible = [item for item in finalists if item["report"]["ready_for_reserved_test"]]
    selected = sorted(eligible, key=rank_report)[0] if eligible else None
    atomic_json(root / "selection.json", {"created_at": stamp(), "status": "ready_for_reserved_test" if selected else "development_requirements_not_met",
                "selected": {k: v for k, v in selected.items() if k != "report"} if selected else None,
                "fits_completed": fits, "maximum_fits": plan["maximum_fits"], "final_test_evaluated": False,
                "finalists": finalists, "source_sha256": sha256(root / "source.json"), "plan_sha256": sha256(root / "plan.json")})
    frames = [read_csv(root / "finalists" / item["id"] / "validation_predictions.csv") for item in finalists]
    keys = [set(zip(f.loc[f.context_windowed.eq("False"), "sample_id"], f.loc[f.context_windowed.eq("False"), "target_id"])) for f in frames]
    common = set.intersection(*keys)
    comparisons = {}
    for item, frame in zip(finalists, frames):
        frame = frame.loc[[key in common for key in zip(frame.sample_id, frame.target_id)]]
        comparisons[item["id"]] = {"pairs": len(frame), "metrics": classification_metrics(frame.label, frame.valence, frame.weight.astype(float))}
    atomic_json(root / "common_complete_context.json", {"scope": "Pares compartidos con contexto completo en ambos modelos; sensibilidad de desarrollo.", "models": comparisons})
    print("TUNING_COMPLETE", "selected=" + (selected["id"] if selected else "none"), "fits=" + str(fits), flush=True)


def export_experiment(settings: dict, run: Path, experiment_id: str, task: str) -> Path:
    root = experiment_directory(run, experiment_id)
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if json.loads((root / "plan.json").read_text()).get("protocol") == "targeted-human-refinement-v1" and relative.parts[0] == "warmstart":
            continue  # Already frozen locally; do not download parent weights again.
        if path.is_file() and not path.name.startswith("export_") and not (relative.parts[0] == "trials" and "model" in relative.parts):
            files[relative.as_posix()] = sha256(path)
    atomic_json(root / f"export_{task}.json", {"experiment_id": experiment_id, "task": task, "files": files,
                "source": json.loads((root / "source.json").read_text()), "final_test_evaluated": False})
    return root / f"export_{task}.json"


def render_comparison(root: Path) -> Path:
    """Render local scientific artifacts without changing the exported model evidence."""
    selection = json.loads((root / "selection.json").read_text())
    source = json.loads((root / "source.json").read_text())
    baseline = json.loads((root / "baseline/validation_report.json").read_text())
    reports = [{"id": "modelo_anterior", "report": baseline}] + selection["finalists"]
    if (root / "reference_beto/validation_report.json").exists():
        reports.insert(1, {"id": "beto_anterior", "report": json.loads((root / "reference_beto/validation_report.json").read_text())})
    if selection.get("final_test_evaluated") is not False or any(item["report"].get("final_test_evaluated") is not False for item in reports):
        raise ValueError("El informe comparativo solo admite resultados de desarrollo")
    rows = []
    for item in reports:
        report = item["report"]
        rows.append({"model": item["id"], "macro_f1": report["raw"]["macro_f1"],
                     "positive_precision": report["accepted"]["classes"]["positive"]["precision"],
                     "negative_precision": report["accepted"]["classes"]["negative"]["precision"],
                     "coverage": report["coverage"], "target_precision": report["target_precision"], "target_recall": report["target_recall"],
                     "incomplete_context_pairs": report["context_incomplete_pairs"],
                     "ready_for_reserved_test": report["ready_for_reserved_test"],
                     "failed_checks": ", ".join(name for name, passed in report["checks"].items() if not passed)})
    folder = root / "report"; folder.mkdir(exist_ok=True)
    frame = pd.DataFrame(rows); frame.to_csv(folder / "comparison.csv", index=False)
    text = ["# Comparación de desarrollo", "", "Validación reutilizada y asistida por IA; los 500 comentarios finales permanecen reservados.", "",
            "| Modelo | Macro-F1 | Precisión positiva aceptada | Precisión negativa aceptada | Cobertura | Preparado para prueba |",
            "|---|---:|---:|---:|---:|---|"]
    for row in rows:
        text.append(f"| {row['model']} | {row['macro_f1']:.4f} | {row['positive_precision']:.2%} | {row['negative_precision']:.2%} | {row['coverage']:.2%} | {'Sí' if row['ready_for_reserved_test'] else 'No'} |")
    text += ["", f"Ajustes completados: {selection['fits_completed']}/{selection['maximum_fits']}.",
             "Candidato seleccionado: " + (selection["selected"]["id"] if selection["selected"] else "ninguno; mantener el bloqueo") + ".", "",
             "La precisión de una clase sin predicciones aceptadas se informa como cero según el criterio del pipeline. La cobertura incluye objetivos omitidos.",
             "Estos valores son de selección sobre desarrollo; no equivalen a una prueba final superada.", ""]
    for row in rows:
        text.append(f"- {row['model']}: criterios pendientes: {row['failed_checks'] or 'ninguno en desarrollo'}.")
    (folder / "comparison.md").write_text("\n".join(text) + "\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for axis, metric, title, threshold in zip(axes, ["macro_f1", "coverage"], ["Macro-F1 ponderado", "Cobertura extremo a extremo"],
                                              [source["quality"]["macro_f1"], source["quality"]["coverage"]]):
        bars = axis.bar(frame.model, frame[metric], color=["#888888", "#377eb8", "#4daf4a"])
        axis.axhline(threshold, color="#b2182b", linestyle="--", label=f"Mínimo {threshold:.0%}")
        axis.set_ylim(0, 1.05); axis.set_title(title); axis.tick_params(axis="x", labelrotation=15)
        axis.bar_label(bars, labels=[f"{value:.1%}" for value in frame[metric]], padding=3); axis.legend(fontsize=8)
    figure.suptitle("Validación de desarrollo · prueba final reservada")
    figure.tight_layout(); figure.savefig(folder / "comparison.png", dpi=180); plt.close(figure)
    return folder
