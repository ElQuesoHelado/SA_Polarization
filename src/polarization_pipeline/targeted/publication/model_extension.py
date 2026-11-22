"""Additive encoder experiment; the original study and benchmark stay immutable."""
from __future__ import annotations

import json
import re
import shutil
import tomllib
import urllib.request
from pathlib import Path

import pandas as pd

from ..common import atomic_json, read_csv, sha256, stamp
from .state import seal, verify, verify_seal, lock

PROTOCOL = "targeted-publication-model-extension-v1"
NEW_MODELS = ("mrbert_es", "mdeberta_v3")
REFERENCES = ("robertuito", "beto", "xlm_roberta")
MODEL_IDS = (*REFERENCES, *NEW_MODELS)


def is_extension(plan):
    return plan.get("model_extension_protocol") == PROTOCOL


def validate(plan):
    expected = dict(maximum_fits=6, model_seeds=[42, 43, 44], maximum_epochs=8,
                    patience=2, effective_batch_size=16, weight_decay=.01,
                    gradient_clip=1., learning_rate=2e-5)
    if (not is_extension(plan) or any(plan.get(k) != v for k, v in expected.items())
            or plan.get("reference_models") != list(REFERENCES)
            or [m["id"] for m in plan.get("models", [])] != list(NEW_MODELS)
            or [m["model"] for m in plan["models"]] != ["BSC-LT/MrBERT-es", "microsoft/mdeberta-v3-base"]):
        raise ValueError("Ampliación requiere dos bases nuevas, tres semillas y receta fija")
    for model in plan["models"]:
        if model["maximum_tokens"] != 512 or model["physical_batch_size"] != 4:
            raise ValueError("Contexto/lote incompatible con la ampliación")
        if model.get("use_fast", False) != (model["id"] == "mrbert_es"):
            raise ValueError("Tokenizador incompatible con la arquitectura")


def verify_extension(study):
    verify(study, frozen=True)
    verify_seal(study, "extension_manifest.json")
    item = json.loads((study / "extension.json").read_text())
    source = Path(item["source_study"])
    verify(source, frozen=True)
    for name, digest in item["source_files"].items():
        if sha256(source / name) != digest:
            raise ValueError("Una referencia de la ampliación cambió")
    benchmark = Path(item["source_benchmark"])
    verify(benchmark, frozen=True)
    verify_seal(benchmark / "predictions")
    if sha256(benchmark / "predictions/manifest.json") != item["benchmark_predictions_sha256"]:
        raise ValueError("Predicciones de referencia modificadas")
    if (study / "annotations/benchmark").resolve() != (source / "annotations/benchmark").resolve():
        raise ValueError("Muestra benchmark redirigida")
    if list((study / "annotations").glob("cohort_*")):
        raise ValueError("La ampliación solo predice el benchmark")
    plan = json.loads((study / "extension_plan.json").read_text())
    validate(plan)
    return item, plan


def view(settings, plan, study, experiment_id, training_config=None, *, create=False):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", experiment_id):
        raise ValueError("experiment-id inválido")
    verify(study, frozen=True)
    folder = study / "model_experiments" / experiment_id
    if not folder.exists():
        if not create or training_config is None:
            raise FileNotFoundError("Preparar primero train --experiment-id ... --training-config ...")
        training_config = Path(training_config)
        if not training_config.is_absolute():
            training_config = settings["_root"] / training_config
        specification = tomllib.loads(training_config.read_text())
        if specification.get("protocol") != PROTOCOL or specification.get("experiment_id") != experiment_id:
            raise ValueError("Identidad/protocolo de ampliación incompatible")
        extended = {**plan, **specification, "protocol": plan["protocol"],
                    "model_extension_protocol": PROTOCOL, "training_config_sha256": sha256(training_config)}
        validate(extended)
        verify_seal(study / "training_input")
        verify_seal(study / "training")
        benchmark = study / "prediction_jobs" / (study.name + "_benchmark_v1")
        verify(benchmark, frozen=True)
        verify_seal(benchmark / "predictions")
        for model in extended["models"]:
            if model["revision"] == "resolve_once":
                with urllib.request.urlopen("https://huggingface.co/api/models/" + model["model"], timeout=60) as response:
                    model["revision"] = json.load(response)["sha"]
            if not re.fullmatch(r"[a-f0-9]{40}", model["revision"]):
                raise ValueError("La revisión debe ser un SHA inmutable")
        sources = ["training_input/manifest.json", "training/manifest.json",
                   "training/shared_training_pairs.csv", "training/shared_validation_pairs.csv", "benchmark.csv"]
        with lock(study / "model_extension.lock"):
            folder.mkdir(parents=True, exist_ok=False)
            snapshot = json.loads((study / "freeze.json").read_text())
            for name in sorted(set(snapshot["files"]) | {"study.json", "freeze.json"}):
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to((study / name).resolve(), target_is_directory=(study / name).is_dir())
            (folder / "annotations").mkdir(exist_ok=True)
            (folder / "annotations/benchmark").symlink_to((study / "annotations/benchmark").resolve(), target_is_directory=True)
            atomic_json(folder / "extension_plan.json", extended)
            atomic_json(folder / "extension.json", dict(protocol=PROTOCOL, experiment_id=experiment_id,
                created_at=stamp(), source_study=str(study.resolve()), source_benchmark=str(benchmark.resolve()),
                source_files={name: sha256(study / name) for name in sources},
                benchmark_predictions_sha256=sha256(benchmark / "predictions/manifest.json"),
                benchmark_previously_examined=True, production_enabled=False, reserved_test_opened=False))
            seal(folder, ["extension.json", "extension_plan.json"], filename="extension_manifest.json")
    _, extended = verify_extension(folder)
    if training_config is not None:
        path = Path(training_config)
        if not path.is_absolute():
            path = settings["_root"] / path
        if sha256(path) != extended["training_config_sha256"]:
            raise ValueError("Configuración distinta del experimento congelado")
    return folder, extended


def prepare_training(settings, plan, parent, study):
    item, frozen = verify_extension(study)
    if plan != frozen:
        raise ValueError("Plan de ampliación distinto del congelado")
    source = Path(item["source_study"])
    folder = study / "training_input"
    if folder.exists():
        verify_seal(folder)
        return folder
    verify_seal(source / "training_input")
    verify_seal(source / "training")
    # Source calls its training file train.csv, but its shared IDs training_pairs.csv.
    def subset(split, key_name):
        original = read_csv(source / "training_input" / f"{split}.csv")
        keys = read_csv(source / "training" / f"shared_{key_name}_pairs.csv")
        fields = ["comment_id", "target_id"]
        if original.duplicated(fields).any() or keys.duplicated(fields).any():
            raise ValueError("Pares de desarrollo duplicados")
        result = keys.merge(original, on=fields, how="left", sort=False, validate="one_to_one", indicator=True)
        if not result._merge.eq("both").all() or not result.split.eq(split).all():
            raise ValueError("Pares compartidos incompatibles con la partición")
        return result.drop(columns="_merge")
    training, validation = subset("train", "training"), subset("validation", "validation")
    if set(training.post_id) & set(validation.post_id):
        raise ValueError("Videos compartidos entre entrenamiento y validación")
    folder.mkdir()
    training.to_csv(folder / "train.csv", index=False)
    validation.to_csv(folder / "validation.csv", index=False)
    atomic_json(folder / "plan.json", {**plan, "frozen_at": stamp(), "reserved_test_exported": False,
        "require_all_context": True, "expected_training_pairs": len(training), "expected_validation_pairs": len(validation),
        "source_shared_training_sha256": sha256(source / "training/shared_training_pairs.csv"),
        "source_shared_validation_sha256": sha256(source / "training/shared_validation_pairs.csv")})
    seal(folder, ["train.csv", "validation.csv", "plan.json"], status="training_only", maximum_fits=6)
    return folder


def combine_predictions(study):
    """Copy three immutable baseline predictions into a fresh five-model view."""
    item, plan = verify_extension(study)
    source = Path(item["source_benchmark"])
    verify_seal(study / "predictions")
    for name in ("prediction_input.csv", "prediction_scope.csv"):
        if sha256(study / name) != sha256(source / name):
            raise ValueError("La entrada del benchmark difiere de la comparación anterior")
    folder = study / "combined"
    if folder.exists():
        verify_seal(folder / "predictions")
        return folder, {**plan, "comparison_model_ids": list(MODEL_IDS)}
    folder.mkdir()
    snapshot = json.loads((study / "freeze.json").read_text())
    for name in sorted(set(snapshot["files"]) | {"study.json", "freeze.json", "prediction_input.csv", "prediction_scope.csv"}):
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to((study / name).resolve(), target_is_directory=(study / name).is_dir())
    (folder / "annotations").mkdir(exist_ok=True)
    (folder / "annotations/benchmark").symlink_to((study / "annotations/benchmark").resolve(), target_is_directory=True)
    destination = folder / "predictions"
    destination.mkdir()
    for model_id in MODEL_IDS:
        origin = source if model_id in REFERENCES else study
        shutil.copy2(origin / "predictions" / f"{model_id}.csv", destination / f"{model_id}.csv")
    seal(destination, [f"{m}.csv" for m in MODEL_IDS],
        prediction_input_sha256=sha256(study / "prediction_input.csv"),
        prediction_scope_sha256=sha256(study / "prediction_scope.csv"),
        new_training_sha256=sha256(study / "training/manifest.json"),
        reference_predictions_sha256=item["benchmark_predictions_sha256"],
        diagnostic_only=True, production_enabled=False, benchmark_previously_examined=True)
    return folder, {**plan, "comparison_model_ids": list(MODEL_IDS)}
