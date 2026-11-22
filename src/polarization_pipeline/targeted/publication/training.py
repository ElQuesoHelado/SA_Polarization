"""Exactly four models x three seeds; new reference labels never enter these inputs."""
from __future__ import annotations

import json
import re
import shutil
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from ..common import LABELS, atomic_json, read_csv, sha256, stamp
from ..development import fit_seed, maximum_length
from ..learning import calibrate, complete_context, predict_logits, probabilities, _gpu
from .state import seal, verify, verify_seal

MODELS = ["pysentimiento/robertuito-base-uncased", "dccuchile/bert-base-spanish-wwm-uncased",
          "bertin-project/bertin-roberta-base-spanish", "FacebookAI/xlm-roberta-base"]


def development_pairs(settings, parent):
    """Verify closure by hashes; skip test rows before decoding any label JSON."""
    from ..diagnostics import load_development
    from ..registry import Matcher, load_registry, registry_fingerprint
    manifest = json.loads((parent / "annotations/manifest.json").read_text())
    if (manifest.get("status") != "human_reviewed_assisted" or manifest.get("gold_sha256") != sha256(parent / "annotations/gold.csv")
            or manifest.get("registry_sha256") != registry_fingerprint(settings["registry"])):
        raise ValueError("Referencia de desarrollo o registro anterior alterados")
    gold, _ = load_development(parent)
    matcher = Matcher(load_registry(settings["registry"], frozen=True))
    rows = []
    for row in gold.to_dict("records"):
        labels = {item["target_id"]: item["valence"] for item in row["items"]}
        for match in matcher.find(row["text"], row["comment_published_at"]):
            rows.append({**{key: row[key] for key in ("comment_id", "post_id", "text", "split")}, **match,
                         "label": labels.get(match["target_id"], "not_evaluable"), "weight": row["weight"]})
    return gold, pd.DataFrame(rows)


def validate_plan(plan):
    from .model_extension import is_extension, validate
    if is_extension(plan):
        return validate(plan)
    expected = dict(maximum_fits=12, model_seeds=[42, 43, 44], maximum_epochs=8, patience=2,
                    effective_batch_size=16, learning_rate=2e-5, weight_decay=.01, gradient_clip=1.)
    if any(plan.get(k) != v for k, v in expected.items()) or [m["model"] for m in plan["models"]] != MODELS:
        raise ValueError("Se requiere la comparación autorizada: cuatro modelos, tres semillas y receta fija")
    if [m["id"] for m in plan["models"]] != ["robertuito", "beto", "bertin", "xlm_roberta"]:
        raise ValueError("Identificadores de modelos incompatibles")
    for model in plan["models"]:
        if model["maximum_tokens"] != 512 or model["physical_batch_size"] != 4:
            raise ValueError("Configuración de contexto/lote no autorizada")


def prepare(settings, plan, parent, study):
    from .model_extension import is_extension, prepare_training
    if is_extension(plan):
        return prepare_training(settings, plan, parent, study)
    verify(study)
    validate_plan(plan)
    folder = study / "training_input"
    if folder.exists():
        verify_seal(folder)
        return folder
    gold, pairs = development_pairs(settings, parent)
    if not gold.split.isin(["train", "validation"]).all() or not pairs.split.isin(["train", "validation"]).all():
        raise ValueError("Prohibido incluir prueba en el paquete de entrenamiento")
    models = json.loads(json.dumps(plan["models"]))
    for model in models:
        if model["revision"] == "resolve_once":
            with urllib.request.urlopen("https://huggingface.co/api/models/"+model["model"], timeout=60) as response:
                model["revision"] = json.load(response)["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", model["revision"]):
            raise ValueError("La revisión del modelo debe ser inmutable")
    folder.mkdir()
    pairs.loc[pairs.split.eq("train")].to_csv(folder / "train.csv", index=False)
    pairs.loc[pairs.split.eq("validation")].to_csv(folder / "validation.csv", index=False)
    atomic_json(folder / "plan.json", {**plan, "models": models, "frozen_at": stamp(),
        "preprocessing": "pysentimiento==0.7.3; preprocess_tweet(lang=es, preprocess_handles=False) for robertuito only",
        "parent_gold_sha256": sha256(parent / "annotations/gold.csv"), "reserved_test_exported": False})
    seal(folder, ["train.csv", "validation.csv", "plan.json"], status="training_only", maximum_fits=12)
    verify(study)
    return folder


def model_frame(frame, model_id):
    result = frame.copy()
    if model_id == "robertuito":
        from pysentimiento.preprocessing import preprocess_tweet
        result["text"] = result.text.map(lambda t: preprocess_tweet(t, lang="es", preprocess_handles=False))
        # Accepted predictions always see the complete transformed input. These
        # offsets are diagnostic only for overlong inputs, which always abstain.
        result["mention_start"] = "0"
        result["mention_end"] = "1"
    return result


def train_worker(settings, study):
    from transformers import AutoConfig, AutoTokenizer
    verify_seal(study / "training_input")
    plan = json.loads((study / "training_input/plan.json").read_text())
    validate_plan(plan)
    training = read_csv(study / "training_input/train.csv")
    validation = read_csv(study / "training_input/validation.csv")
    if set(training.split) != {"train"} or set(validation.split) != {"validation"} or set(training.post_id) & set(validation.post_id):
        raise ValueError("Entrenamiento/validación incompatibles o videos compartidos")
    root = study / "training"
    root.mkdir(exist_ok=True)
    common_train, common_validation = np.ones(len(training), dtype=bool), np.ones(len(validation), dtype=bool)
    capacities = {}
    for spec in plan["models"]:
        tokenizer = AutoTokenizer.from_pretrained(spec["model"], revision=spec["revision"], use_fast=spec.get("use_fast", False))
        cfg = AutoConfig.from_pretrained(spec["model"], revision=spec["revision"])
        maximum = maximum_length(cfg, tokenizer, spec["maximum_tokens"])
        capacities[spec["id"]] = maximum
        common_train &= complete_context(tokenizer, model_frame(training, spec["id"]), maximum)
        common_validation &= complete_context(tokenizer, model_frame(validation, spec["id"]), maximum)
    if not common_train.any() or not common_validation.any():
        raise ValueError("No hay contexto completo común a los cuatro modelos")
    if plan.get('require_all_context') and (not common_train.all() or not common_validation.all()
            or len(training) != plan['expected_training_pairs'] or len(validation) != plan['expected_validation_pairs']):
        raise ValueError('La ampliación debe conservar todos los pares originales con contexto completo')
    shared_training, shared_validation = training.loc[common_train], validation.loc[common_validation]
    shared_training[["comment_id", "target_id"]].to_csv(root / "shared_training_pairs.csv", index=False)
    shared_validation[["comment_id", "target_id"]].to_csv(root / "shared_validation_pairs.csv", index=False)
    atomic_json(root / "common_context.json", dict(capacities=capacities, train_total=len(training), train_shared=len(shared_training),
        validation_total=len(validation), validation_shared=len(shared_validation)))
    results = []
    for spec in plan["models"]:
        folder = root / spec["id"]
        model_dir = folder / "model"
        model_dir.mkdir(parents=True, exist_ok=True)
        fit = model_frame(shared_training, spec["id"])
        val = model_frame(shared_validation, spec["id"])
        revisions, logits = [], []
        for seed in plan["model_seeds"]:
            record = folder / f"fit_{seed}.json"
            if record.exists():
                item = json.loads(record.read_text())
                for name, digest in item["files"].items():
                    if sha256(folder / name) != digest:
                        raise ValueError("Checkpoint completado alterado; no reentrenar silenciosamente")
                values = np.load(model_dir / f"validation_logits_{seed}.npy", allow_pickle=False)
                revision = item["revision"]
            else:
                if (model_dir / str(seed)).exists():
                    raise ValueError("Ajuste interrumpido: conservar checkpoint parcial y diagnosticar, no repetir automáticamente")
                trial = dict(id=spec["id"], learning_rate=plan["learning_rate"], objective="class_balanced")
                revision, values = fit_seed(settings, fit, val, model_dir, spec, trial, plan, seed)
                files = [*sorted((model_dir / str(seed)).rglob("*")), model_dir / f"validation_logits_{seed}.npy"]
                atomic_json(record, dict(revision=revision, files={str(p.relative_to(folder)): sha256(p) for p in files if p.is_file()}))
            revisions.append(revision); logits.append(values)
        mean = np.mean([probabilities(v) for v in logits], axis=0)
        calibration = calibrate(np.log(mean.clip(1e-12)), val.label.to_numpy(), val.weight.astype(float).to_numpy(),
                                settings["quality"]["valence_precision"])
        atomic_json(model_dir / "calibration.json", calibration)
        atomic_json(model_dir / "training_manifest.json", dict(model=spec, revisions=revisions, maximum_tokens=capacities[spec["id"]],
            calibration=calibration, stage="diagnostic_only", reserved_test_opened=False,
            shared_training_pairs_sha256=sha256(root / "shared_training_pairs.csv"),
            shared_validation_pairs_sha256=sha256(root / "shared_validation_pairs.csv")))
        selected = mean.argmax(axis=1)
        from ..learning import classification_metrics
        metrics = classification_metrics(val.label, np.array(LABELS)[selected], val.weight.astype(float))
        results.append(dict(model_id=spec["id"], metrics=metrics, calibration=calibration))
    atomic_json(root / "comparison.json", dict(models=results, completed_fits=plan['maximum_fits'], production_enabled=False,
        evaluation_reference_used=False, training_input_sha256=sha256(study / "training_input/manifest.json"),
        selection_basis="reused_assisted_validation_only"))
    seal(root, [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name != "manifest.json"], status="complete")


def prediction_comments(study):
    verify(study, frozen=True)
    frames = [read_csv(study / "benchmark.csv")]
    for path in sorted((study / "annotations").glob("cohort_*/sample.csv")):
        frames.append(read_csv(path))
    return pd.concat(frames, ignore_index=True).drop_duplicates("comment_id")


def prediction_pairs(study, registry):
    from ..registry import Matcher, load_registry
    comments = prediction_comments(study)
    matcher = Matcher(load_registry(registry, frozen=True))
    rows = []
    for row in comments.to_dict("records"):
        for candidate in matcher.find(row["text"], row["comment_published_at"]):
            rows.append({**{k: row[k] for k in ("sample_id", "comment_id", "post_id", "text", "comment_published_at")}, **candidate})
    return pd.DataFrame(rows)


def predict_worker(settings, study):
    from transformers import AutoTokenizer
    from ..targetaware import load_classifier
    verify_seal(study / "training")
    pairs = read_csv(study / "prediction_input.csv")
    if "label" in pairs or "annotation_json" in pairs:
        raise ValueError("La inferencia diagnóstica no recibe etiquetas")
    destination = study / "predictions"
    destination.mkdir(exist_ok=False)
    ids = [m['model_id'] for m in json.loads((study / 'training/comparison.json').read_text())['models']]
    for model_id in ids:
        folder = study / "training" / model_id / "model"
        manifest = json.loads((folder / "training_manifest.json").read_text())
        transformed = model_frame(pairs, model_id)
        all_probs = []
        for revision in manifest["revisions"]:
            checkpoint = folder / str(revision["seed"])
            tokenizer = AutoTokenizer.from_pretrained(checkpoint, use_fast=manifest['model'].get('use_fast', False))
            classifier = load_classifier(checkpoint).cuda()
            logits = predict_logits(classifier, tokenizer, transformed, manifest["maximum_tokens"], batch_size=4)
            all_probs.append(probabilities(logits))
            del classifier
            _gpu().cuda.empty_cache()
        mean = np.mean(all_probs, axis=0)
        calibration = manifest["calibration"]
        calibrated = probabilities(np.log(mean.clip(1e-12)), calibration["temperature"])
        complete = complete_context(tokenizer, transformed, manifest["maximum_tokens"])
        result = pairs[["sample_id", "comment_id", "post_id", "target_id"]].copy()
        result["valence"] = np.array(LABELS)[calibrated.argmax(axis=1)]
        result["confidence"] = calibrated.max(axis=1)
        result["context_complete"] = complete
        result["accepted"] = [bool(c and p >= calibration["thresholds"][v]) for c, p, v in zip(complete, result.confidence, result.valence)]
        result["model_id"] = model_id
        result.to_csv(destination / f"{model_id}.csv", index=False)
    seal(destination, [f"{m}.csv" for m in ids], prediction_input_sha256=sha256(study / "prediction_input.csv"),
         prediction_scope_sha256=sha256(study / "prediction_scope.csv"), training_sha256=sha256(study / "training/manifest.json"),
         diagnostic_only=True, production_enabled=False)
