"""Target markers from automatic offsets, bounded experiments, and diagnostics."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import LABELS, atomic_json, read_csv, sha256, stamp

PROTOCOL = "targeted-target-aware-v1"
MARKERS = ("[TGT]", "[/TGT]")
REPRESENTATIONS = ("marked_cls", "marked_target_max")


def representation(tokenizer) -> str:
    value = getattr(tokenizer, "init_kwargs", {}).get("target_representation", "pair_cls")
    if value not in ("pair_cls", *REPRESENTATIONS):
        raise ValueError("Representación de entrada desconocida")
    return value


def marked_example(tokenizer, row: dict, maximum: int | None = None) -> dict:
    """Insert marker IDs at known automatic spans; literal markers cannot alter the mask."""
    text = row["text"]
    start, end = int(row["mention_start"]), int(row["mention_end"])
    if not 0 <= start < end <= len(text) or not text[start:end].strip():
        raise ValueError("Offsets automáticos de mención inválidos")
    opening, closing = tokenizer.convert_tokens_to_ids(list(MARKERS))
    if opening == closing or tokenizer.unk_token_id in (opening, closing):
        raise ValueError("Faltan los marcadores del objetivo en el tokenizador")
    target = tokenizer.encode(row["target_name"], add_special_tokens=False)
    before = tokenizer.encode(text[:start], add_special_tokens=False)
    mention = tokenizer.encode(text[start:end], add_special_tokens=False)
    after = tokenizer.encode(text[end:], add_special_tokens=False)
    if not mention:
        raise ValueError("Mención sin tokens")
    # Full lengths are always checked first. Windowing is diagnostic only.
    if maximum is not None:
        available = maximum - len(target) - tokenizer.num_special_tokens_to_add(pair=True) - 2 - len(mention)
        if available < 0:
            raise ValueError("La mención no cabe en la ventana del modelo")
        left = min(len(before), available // 2)
        right = min(len(after), available - left)
        left = min(len(before), available - right)
        before, after = (before[-left:] if left else []), after[:right]
    comment = before + [opening] + mention + [closing] + after
    ids = tokenizer.build_inputs_with_special_tokens(target, comment)
    types = tokenizer.create_token_type_ids_from_sequences(target, comment)
    offset = len(tokenizer.build_inputs_with_special_tokens(target, [])) - 1 + len(before) + 1
    mask = [0] * len(ids)
    mask[offset:offset + len(mention)] = [1] * len(mention)
    if any(types[i] != 1 for i, value in enumerate(mask) if value):
        raise ValueError("Máscara fuera del comentario")
    return {"input_ids": ids, "token_type_ids": types, "attention_mask": [1] * len(ids), "target_mask": mask}


def input_lengths(tokenizer, frame: pd.DataFrame) -> np.ndarray:
    return np.array([len(marked_example(tokenizer, row)["input_ids"]) for row in frame.to_dict("records")])


def marked_encoding(tokenizer, rows: list[dict], maximum: int):
    import torch
    if tokenizer.padding_side != "right":
        raise ValueError("BETO marcado requiere padding a la derecha")
    examples = [marked_example(tokenizer, row, maximum) for row in rows]
    masks = [example.pop("target_mask") for example in examples]
    encoded = tokenizer.pad(examples, padding=True, return_tensors="pt")
    if representation(tokenizer) == "marked_target_max":
        length = encoded["input_ids"].shape[1]
        encoded["target_mask"] = torch.tensor([mask + [0] * (length - len(mask)) for mask in masks], dtype=torch.bool)
    return encoded


def load_classifier(path, **kwargs):
    from transformers import AutoConfig, AutoModelForSequenceClassification
    config = kwargs.pop("config", None)
    if config is None:
        config = AutoConfig.from_pretrained(path, **{k: v for k, v in kwargs.items() if k == "revision"})
    value = getattr(config, "target_representation", "pair_cls")
    if value not in ("pair_cls", *REPRESENTATIONS):
        raise ValueError("Representación del checkpoint desconocida")
    if value != "pair_cls" and config.model_type != "bert":
        raise ValueError("Marcadores reservados para la arquitectura BERT")
    if value == "marked_target_max":
        from .target_model import TargetMaxBertForSequenceClassification
        return TargetMaxBertForSequenceClassification.from_pretrained(path, config=config, **kwargs)
    if config.model_type == 'modernbert':
        config.reference_compile = False
        kwargs.setdefault('attn_implementation', 'sdpa')
    return AutoModelForSequenceClassification.from_pretrained(path, config=config, **kwargs)


def initialize_model(model_spec: dict):
    from transformers import AutoConfig, AutoTokenizer
    import inspect
    tokenizer = AutoTokenizer.from_pretrained(model_spec["model"], revision=model_spec["revision"], use_fast=model_spec.get('use_fast', False))
    value = model_spec.get("representation", "pair_cls")
    config = AutoConfig.from_pretrained(model_spec["model"], revision=model_spec["revision"], num_labels=len(LABELS),
                                      id2label=dict(enumerate(LABELS)), label2id={label: i for i, label in enumerate(LABELS)})
    if value != "pair_cls":
        if value not in REPRESENTATIONS:
            raise ValueError("Representación de entrenamiento desconocida")
        config.target_representation = value
        config.classifier_dropout = 0.1
        tokenizer.add_special_tokens({"additional_special_tokens": list(MARKERS)})
        tokenizer.init_kwargs["target_representation"] = value
    model = load_classifier(model_spec["model"], revision=model_spec["revision"], config=config)
    if value != "pair_cls":
        # Support transformers 4.40 as well as releases with mean initialization.
        options = {"mean_resizing": False} if "mean_resizing" in inspect.signature(model.resize_token_embeddings).parameters else {}
        model.resize_token_embeddings(len(tokenizer), **options)
    return model, tokenizer


def validate_plan(plan: dict) -> None:
    expected = {"maximum_fits": 6, "final_seeds": [42, 43, 44], "effective_batch_size": 16,
                "learning_rates": [1e-5], "objectives": ["class_balanced"], "maximum_epochs": 8,
                "patience": 2, "weight_decay": 0.01, "gradient_clip": 1.0}
    if any(plan.get(key) != value for key, value in expected.items()):
        raise ValueError("La ronda dirigida debe conservar sus seis ajustes y parámetros autorizados")
    specs = plan.get("models", [])
    if [s.get("id") for s in specs] != ["beto_marked_cls", "beto_target_max"] or not plan.get("parent_experiment_id"):
        raise ValueError("Variantes o referencia padre incompatibles")
    for spec, value in zip(specs, REPRESENTATIONS):
        if (spec.get("representation") != value or spec.get("model") != "dccuchile/bert-base-spanish-wwm-uncased"
                or spec.get("revision") != "d1c9c4565c9d6731e57ed7f027b802697bad861e"
                or spec.get("maximum_tokens") != 512 or spec.get("physical_batch_size") != 4):
            raise ValueError("Arquitectura o revisión distinta de la ronda autorizada")


def parent_reference(settings: dict, run: Path, plan: dict) -> tuple[dict, dict]:
    from .development import experiment_directory, verify_source
    parent = experiment_directory(run, plan["parent_experiment_id"])
    verify_source(settings, run, parent)
    selection = json.loads((parent / "selection.json").read_text())
    if selection.get("final_test_evaluated") is not False or selection.get("fits_completed") != 12:
        raise ValueError("La referencia padre debe ser una comparación de desarrollo completada")
    export = json.loads((parent / "export_tune.json").read_text())
    receipt = json.loads((parent / "import_tune.json").read_text())
    if receipt.get("final_test_evaluated") is not False or export.get("source") != json.loads((parent / "source.json").read_text()):
        raise ValueError("Procedencia del padre incompatible")
    paths = {}
    for folder, destination in [("baseline", "baseline"), ("finalists/beto", "reference_beto")]:
        for path in sorted((parent / folder).glob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(parent).as_posix()
            if export["files"].get(relative) != sha256(path):
                raise ValueError("Informe padre alterado")
            paths[f"{destination}/{path.name}"] = path
    for required in ["baseline/manifest.json", "baseline/validation_report.json", "reference_beto/validation_report.json", "reference_beto/validation_predictions.csv"]:
        if required not in paths:
            raise ValueError("Faltan diagnósticos de referencia")
    provenance = {"experiment_id": parent.name, "plan_sha256": sha256(parent / "plan.json"),
                  "source_sha256": sha256(parent / "source.json"), "export_sha256": sha256(parent / "export_tune.json"),
                  "import_sha256": sha256(parent / "import_tune.json"), "files": {name: sha256(path) for name, path in paths.items()}}
    return provenance, paths


def diagnostic_slices(gold: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    from .learning import classification_metrics
    lookup = {(r.sample_id, r.target_id): r for r in predictions.itertuples()}
    weights = {key: 0.0 for key in ("missed_target", "incomplete_context", "low_confidence", "accepted")}
    counts = dict.fromkeys(weights, 0)
    for row in gold.itertuples():
        for target in json.loads(row.annotation_json):
            if target["valence"] not in LABELS[:3]:
                continue
            prediction = lookup.get((row.sample_id, target["target_id"]))
            reason = ("missed_target" if prediction is None else "incomplete_context" if prediction.context_windowed
                      else "accepted" if prediction.accepted else "low_confidence")
            weights[reason] += 1 / float(row.sampling_probability)
            counts[reason] += 1
    total = sum(weights.values())
    multiple = predictions.groupby("sample_id").target_id.transform("size").gt(1)
    return {"coverage_decomposition": {key: {"units": counts[key], "weighted_share": value / total if total else 0.0}
                                       for key, value in weights.items()},
            "by_target_count": {name: {"pairs": len(frame), "metrics": classification_metrics(frame.label, frame.valence, frame.weight.astype(float))}
                                for name, frame in [("single", predictions.loc[~multiple]), ("multiple", predictions.loc[multiple])]},
            "neutral_confusion": predictions.loc[predictions.label.eq("neutral")].valence.value_counts().to_dict()}


def tune_targetaware(settings: dict, run: Path, root: Path, gold: pd.DataFrame, pairs: pd.DataFrame, plan: dict, source: dict) -> None:
    from .development import fit_seed, finish_model, rank_report, verify_accumulation
    from .learning import classification_metrics
    validate_plan(plan)
    if not (root / "reference_beto/validation_report.json").exists() or (root / "trials").exists():
        raise ValueError("Falta referencia BETO o ya se inició esta ronda; no repetir ajustes")
    verify_accumulation()
    from .target_selftest import verify_target_models
    verify_target_models()
    (root / "trials").mkdir()
    training, validation = pairs.loc[pairs.split.eq("train")].copy(), pairs.loc[pairs.split.eq("validation")].copy()
    finalists, fits = [], 0
    for spec in plan["models"]:
        trial = {"id": spec["id"], "learning_rate": 1e-5, "objective": "class_balanced"}
        path = root / "finalists" / spec["id"]
        revisions, logits = [], []
        for seed in plan["final_seeds"]:
            if fits >= plan["maximum_fits"]:
                raise ValueError("Presupuesto de entrenamiento agotado")
            atomic_json(root / "progress.json", {"fits_started": fits + 1, "fits_completed": fits, "variant": spec["id"], "seed": seed, "final_test_evaluated": False})
            revision, values = fit_seed(settings, training, validation, path / "model", spec, trial, plan, seed)
            revisions.append(revision); logits.append(values); fits += 1
            atomic_json(root / "progress.json", {"fits_started": fits, "fits_completed": fits, "variant": spec["id"], "seed": seed, "final_test_evaluated": False})
        report = finish_model(settings, run, source, path, spec, trial, validation, revisions, logits)
        finalists.append({"id": spec["id"], "report": report, "trial_id": trial["id"], "model_path": str(path.relative_to(root) / "model")})
    eligible = sorted([item for item in finalists if item["report"]["ready_for_reserved_test"]], key=rank_report)
    selected = eligible[0] if eligible else None
    atomic_json(root / "selection.json", {"created_at": stamp(), "status": "ready_for_reserved_test" if selected else "development_requirements_not_met",
                "selected": {k: v for k, v in selected.items() if k != "report"} if selected else None,
                "fits_completed": fits, "maximum_fits": plan["maximum_fits"], "final_test_evaluated": False,
                "finalists": finalists, "source_sha256": sha256(root / "source.json"), "plan_sha256": sha256(root / "plan.json")})
    frames = {"beto_anterior": read_csv(root / "reference_beto/validation_predictions.csv"),
              **{item["id"]: read_csv(root / "finalists" / item["id"] / "validation_predictions.csv") for item in finalists}}
    keys = [set(zip(f.loc[f.context_windowed.eq("False"), "sample_id"], f.loc[f.context_windowed.eq("False"), "target_id"])) for f in frames.values()]
    common = set.intersection(*keys)
    comparisons = {}
    for name, frame in frames.items():
        frame = frame.loc[[key in common for key in zip(frame.sample_id, frame.target_id)]]
        comparisons[name] = {"pairs": len(frame), "metrics": classification_metrics(frame.label, frame.valence, frame.weight.astype(float))}
    atomic_json(root / "common_complete_context.json", {"scope": "Pares compartidos con contexto completo; comparación de desarrollo con BETO anterior.", "models": comparisons})
    print("TUNING_COMPLETE", "selected=" + (selected["id"] if selected else "none"), "fits=" + str(fits), flush=True)
