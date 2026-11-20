"""GPU-only target-conditioned learning. Imports torch/transformers lazily."""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

from .annotations import training_pairs
from .common import LABELS, atomic_json, read_csv, sha256, stamp
from .registry import Matcher, load_registry


def probabilities(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    scores = logits / temperature
    scores = scores - scores.max(axis=1, keepdims=True)
    exponent = np.exp(scores)
    return exponent / exponent.sum(axis=1, keepdims=True)


def classification_metrics(truth, predicted, weights=None) -> dict:
    truth, predicted = np.asarray(truth), np.asarray(predicted)
    weights = np.ones(len(truth)) if weights is None else np.asarray(weights, dtype=float)
    classes = {}
    for label in LABELS:
        tp = float(weights[(truth == label) & (predicted == label)].sum())
        fp = float(weights[(truth != label) & (predicted == label)].sum())
        fn = float(weights[(truth == label) & (predicted != label)].sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        classes[label] = {"precision": precision, "recall": recall,
                          "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
                          "support": int((truth == label).sum())}
    return {"classes": classes, "macro_f1": float(np.mean([classes[label]["f1"] for label in LABELS[:3]]))}


def calibrate(logits: np.ndarray, truth: np.ndarray, weights: np.ndarray, precision: float, valid_input=None) -> dict:
    valid_input = np.ones(len(truth), dtype=bool) if valid_input is None else valid_input
    y = np.array([LABELS.index(label) for label in truth])
    temperatures = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
    temperature = min(temperatures, key=lambda t: np.average(-np.log(probabilities(logits, t)[np.arange(len(y)), y].clip(1e-12)), weights=weights))
    probs = probabilities(logits, temperature)
    pred = probs.argmax(axis=1)
    confidence = probs.max(axis=1)
    thresholds = {}
    for index, label in enumerate(LABELS):
        threshold = 1.01
        for value in np.arange(0.5, 1.0, 0.05):
            mask = (pred == index) & (confidence >= value) & valid_input
            if mask.sum() >= 10 and np.average(y[mask] == index, weights=weights[mask]) >= precision:
                threshold = float(round(value, 2))
                break
        thresholds[label] = threshold
    return {"temperature": temperature, "thresholds": thresholds, "precision_target": precision}


def encoding(tokenizer, rows: list[dict], maximum: int):
    """Keep the target mention in long inputs; no channel/group/user features."""
    from .targetaware import representation, marked_encoding
    if representation(tokenizer) != "pair_cls":
        return marked_encoding(tokenizer, rows, maximum)
    texts, targets = [], []
    for row in rows:
        text = row["text"]
        tokens = tokenizer.encode(text, add_special_tokens=False)
        prefix = tokenizer.encode(text[:int(row["mention_start"])], add_special_tokens=False)
        target_length = len(tokenizer.encode(row["target_name"], add_special_tokens=False))
        special = tokenizer.num_special_tokens_to_add(pair=True)
        budget = max(16, maximum - target_length - special)
        start = max(0, min(len(prefix) - budget // 2, len(tokens) - budget))
        window = text if len(tokens) <= budget else tokenizer.decode(tokens[start:start + budget], skip_special_tokens=True)
        texts.append(window)
        targets.append(row["target_name"])
    return tokenizer(targets, texts, padding=True, truncation="only_second", max_length=maximum, return_tensors="pt")


def complete_context(tokenizer, frame: pd.DataFrame, maximum: int) -> np.ndarray:
    from .targetaware import representation, input_lengths
    if representation(tokenizer) != "pair_cls":
        return input_lengths(tokenizer, frame) <= maximum
    return np.array([len(tokenizer.encode(row.text, add_special_tokens=False)) + len(tokenizer.encode(row.target_name, add_special_tokens=False)) + tokenizer.num_special_tokens_to_add(pair=True) <= maximum for row in frame.itertuples(index=False)], dtype=bool)


def _gpu():
    try:
        import torch
    except ImportError:
        raise RuntimeError("Instala el extra targeted-training en el entorno GPU de Kaggle") from None
    if not torch.cuda.is_available():
        raise RuntimeError("El entrenamiento y la inferencia dirigida requieren GPU; usa el kernel Kaggle preparado")
    return torch


def predict_logits(model, tokenizer, frame: pd.DataFrame, maximum: int, batch_size: int = 32) -> np.ndarray:
    torch = _gpu()
    model.eval()
    values = []
    records = frame.to_dict("records")
    with torch.no_grad():
        for start in range(0, len(records), batch_size):
            inputs = {key: value.cuda() for key, value in encoding(tokenizer, records[start:start + batch_size], maximum).items()}
            values.append(model(**inputs).logits.float().cpu().numpy())
    return np.concatenate(values) if values else np.empty((0, len(LABELS)))


def train(settings: dict, run: Path) -> None:
    frame = training_pairs(settings, run)  # Fail before downloading/loading GPU models if humans have not finished.
    training = frame.loc[frame.split.eq("train")].copy()
    validation = frame.loc[frame.split.eq("validation")].copy()
    if not set(LABELS[:3]) <= set(training.label) or validation.empty:
        raise ValueError("La anotación no contiene las clases o validación necesarias")
    torch = _gpu()
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    from huggingface_hub import model_info
    folder = run / "model"
    folder.mkdir(exist_ok=False)
    base_revision = model_info(settings["base_model"]).sha
    tokenizer = AutoTokenizer.from_pretrained(settings["base_model"], revision=base_revision, use_fast=False)
    validation_logits = []
    revisions = []
    for seed in settings["model_seeds"]:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        model = AutoModelForSequenceClassification.from_pretrained(settings["base_model"], revision=base_revision, num_labels=len(LABELS),
                    id2label=dict(enumerate(LABELS)), label2id={label: i for i, label in enumerate(LABELS)}).cuda()
        maximum = min(512, int(model.config.max_position_embeddings) - 2, int(tokenizer.model_max_length))
        seed_training = training.loc[complete_context(tokenizer, training, maximum)]
        if not set(LABELS[:3]) <= set(seed_training.label):
            raise ValueError("Las clases no tienen ejemplos con contexto completo para esta arquitectura")
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)
        destination = folder / str(seed)
        destination.mkdir()
        best, patience = float("inf"), 0
        history = []
        class_counts = training.label.value_counts()
        class_weight = np.array([1 / np.sqrt(max(1, class_counts.get(label, 0))) for label in LABELS])
        loss_function = torch.nn.CrossEntropyLoss(weight=torch.tensor(class_weight / class_weight.mean(), dtype=torch.float, device="cuda"))
        for epoch in range(5):
            model.train()
            records = seed_training.sample(frac=1, random_state=seed + epoch).to_dict("records")
            for start in range(0, len(records), 16):
                batch = records[start:start + 16]
                inputs = {key: value.cuda() for key, value in encoding(tokenizer, batch, maximum).items()}
                labels = torch.tensor([LABELS.index(row["label"]) for row in batch], device="cuda")
                optimizer.zero_grad()
                loss = loss_function(model(**inputs).logits, labels)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            logits = predict_logits(model, tokenizer, validation, maximum)
            prob = probabilities(logits)
            y = np.array([LABELS.index(label) for label in validation.label])
            validation_loss = float(np.average(-np.log(prob[np.arange(len(y)), y].clip(1e-12)), weights=validation.weight.astype(float)))
            history.append({"epoch": epoch + 1, "validation_loss": validation_loss})
            print(f"Semilla {seed}, época {epoch + 1}: pérdida validación {validation_loss:.4f}", flush=True)
            if validation_loss < best:
                best, patience = validation_loss, 0
                model.save_pretrained(destination, safe_serialization=True)
                tokenizer.save_pretrained(destination)
            else:
                patience += 1
                if patience >= 2:
                    break
        del model
        torch.cuda.empty_cache()
        selected = AutoModelForSequenceClassification.from_pretrained(destination).cuda()
        validation_logits.append(predict_logits(selected, tokenizer, validation, maximum))
        revisions.append({"seed": seed, "base_revision": base_revision, "maximum_tokens": maximum, "history": history})
        del selected
        torch.cuda.empty_cache()
    # Average probabilities, represented as log-probabilities, not incompatible raw logit scales.
    ensemble = np.mean([probabilities(item) for item in validation_logits], axis=0)
    calibration = calibrate(np.log(ensemble.clip(1e-12)), validation.label.to_numpy(), validation.weight.astype(float).to_numpy(), settings["quality"]["valence_precision"], complete_context(tokenizer, validation, maximum))
    atomic_json(folder / "calibration.json", calibration)
    annotation_manifest = json.loads((run / "annotations" / "manifest.json").read_text())
    atomic_json(folder / "training_manifest.json", {
        "created_at": stamp(), "status": "trained_awaiting_reserved_test" if annotation_manifest.get("annotation_protocol") == "ai_assisted_single_human_v1" else "trained_awaiting_blind_test", "base_model": settings["base_model"],
        "revisions": revisions,
        "annotation_protocol": annotation_manifest.get("annotation_protocol", "two_independent_humans"),
        "annotation_limitation": annotation_manifest.get("annotation_limitation"),
        "method_version": settings.get("method_version", "targeted-v1"),
        "annotation_lineage_sha256": annotation_manifest.get("inheritance_sha256"),
        "sampling_probability_scope": annotation_manifest.get("sampling_probability_scope"),
        "sampling_split_seed": annotation_manifest.get("sampling_split_seed", settings.get("seed")),
        "gold_sha256": json.loads((run / "annotations" / "manifest.json").read_text()).get("study_gold_sha256", sha256(run / "annotations" / "gold.csv")),
        "training_annotation_sha256": sha256(run / "annotations" / "gold.csv"),
        "registry_sha256": sha256(settings["registry"]), "pair_sha256": sha256(run / "training_pairs.csv"),
        "checkpoint_hashes": {str(path.relative_to(folder)): sha256(path) for path in folder.rglob("*") if path.is_file()},
    })


def ensemble_predict(settings: dict, run: Path, frame: pd.DataFrame, *, model_folder: Path | None = None) -> pd.DataFrame:
    torch = _gpu()
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    from .targetaware import load_classifier, representation
    folder = model_folder if model_folder is not None else run / "model"
    manifest = json.loads((folder / "training_manifest.json").read_text())
    if manifest["registry_sha256"] != sha256(settings["registry"]):
        raise ValueError("Registro distinto del utilizado en entrenamiento")
    for name, digest in manifest["checkpoint_hashes"].items():
        if sha256(folder / name) != digest:
            raise ValueError(f"Checkpoint alterado: {name}")
    all_probabilities = []
    context_complete = None
    for revision in manifest["revisions"]:
        path = folder / str(revision["seed"])
        tokenizer = AutoTokenizer.from_pretrained(path, use_fast=False)
        model = load_classifier(path).cuda()
        if representation(tokenizer) != getattr(model.config, "target_representation", "pair_cls"):
            raise ValueError("Tokenizador y checkpoint usan representaciones distintas")
        if revision.get("representation", "pair_cls") != representation(tokenizer):
            raise ValueError("Representación distinta del manifiesto de entrenamiento")
        if context_complete is None:
            context_complete = complete_context(tokenizer, frame, revision["maximum_tokens"])
        all_probabilities.append(probabilities(predict_logits(model, tokenizer, frame, revision["maximum_tokens"])))
        del model
        torch.cuda.empty_cache()
    calibration = json.loads((folder / "calibration.json").read_text())
    average = np.mean(all_probabilities, axis=0)
    calibrated = probabilities(np.log(average.clip(1e-12)), calibration["temperature"])
    result = frame.copy()
    result["valence"] = [LABELS[i] for i in calibrated.argmax(axis=1)]
    result["confidence"] = calibrated.max(axis=1)
    result["accepted"] = [float(confidence) >= calibration["thresholds"][label] for label, confidence in zip(result.valence, result.confidence)]
    result["context_windowed"] = ~context_complete
    result["accepted"] &= context_complete
    result["abstention_reason"] = np.where(~context_complete, "context_exceeds_validated_model_window", np.where(result.accepted, "", "confidence_below_threshold"))
    for i, label in enumerate(LABELS):
        result[f"p_{label}"] = calibrated[:, i]
    result["seed_disagreement"] = np.std(all_probabilities, axis=0).max(axis=1)
    for revision, seed_probs in zip(manifest["revisions"], all_probabilities):
        calibrated_seed = probabilities(np.log(seed_probs.clip(1e-12)), calibration["temperature"])
        for i, label in enumerate(LABELS):
            result[f"seed_{revision['seed']}_p_{label}"] = calibrated_seed[:, i]
    return result


def evaluation_report(settings: dict, gold: pd.DataFrame, pairs: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    weights = predictions.weight.astype(float).to_numpy()
    predicted = predictions.valence.to_numpy()
    truth = predictions.label.to_numpy()
    raw = classification_metrics(truth, predicted, weights)
    accepted = predictions.accepted.astype(str).str.lower().isin(["true", "1"]).to_numpy()
    selective = classification_metrics(truth[accepted], predicted[accepted], weights[accepted])
    matcher = Matcher(load_registry(settings["registry"]))
    tp = fp = fn = evaluable_gold = covered_gold = 0.0
    # End-to-end coverage denominator includes targets omitted by the generator.
    for row in gold.to_dict("records"):
        weight = 1 / float(row["sampling_probability"])
        targets = {item["target_id"]: item["valence"] for item in json.loads(row["annotation_json"])}
        found = {item["target_id"] for item in matcher.find(row["text"], row["comment_published_at"])}
        tp += weight * len(set(targets) & found)
        fp += weight * len(found - set(targets))
        fn += weight * len(set(targets) - found)
        applicable = {target for target, label in targets.items() if label in LABELS[:3]}
        evaluated = predictions.loc[predictions.sample_id.eq(row["sample_id"]) & predictions.accepted.astype(str).str.lower().isin(["true", "1"])]
        evaluable_gold += weight * len(applicable)
        covered_gold += weight * len(applicable & set(evaluated.target_id))
    target_precision = tp / (tp + fp) if tp + fp else 0.0
    target_recall = tp / (tp + fn) if tp + fn else 0.0
    coverage = covered_gold / evaluable_gold if evaluable_gold else 0.0
    checks = {"target_precision": target_precision >= settings["quality"]["target_precision"],
              "target_recall": target_recall >= settings["quality"]["target_recall"],
              "macro_f1": raw["macro_f1"] >= settings["quality"]["macro_f1"],
              "positive_precision": selective["classes"]["positive"]["precision"] >= settings["quality"]["valence_precision"],
              "negative_precision": selective["classes"]["negative"]["precision"] >= settings["quality"]["valence_precision"],
              "coverage": coverage >= settings["quality"]["coverage"]}
    groups = {}
    for group, subset in predictions.groupby("target_group"):
        groups[group] = classification_metrics(subset.label, subset.valence, subset.weight.astype(float))
    baseline = {"status": "unavailable_for_these_cases"}
    if "sentimiento" in predictions:
        matched = predictions.loc[predictions.sentimiento.isin(LABELS[:3])]
        if len(matched):
            baseline = {"status": "matched_cases", "pairs": len(matched),
                        "general_sentiment": classification_metrics(matched.label, matched.sentimiento, matched.weight.astype(float)),
                        "target_conditioned": classification_metrics(matched.label, matched.valence, matched.weight.astype(float)),
                        "scope": "Solo pares con clasificación histórica disponible; respuestas sin baseline no se imputan."}
    rng = np.random.default_rng(settings["seed"])
    videos = predictions.post_id.unique()
    draws = {"macro_f1": [], "positive_precision": [], "negative_precision": []}
    for _ in range(settings.get("bootstrap_iterations", 2000)):
        counts = rng.multinomial(len(videos), np.full(len(videos), 1 / len(videos))) if len(videos) else []
        draw_weights = predictions.post_id.map(dict(zip(videos, counts))).to_numpy() * weights
        raw_draw = classification_metrics(truth, predicted, draw_weights)
        accepted_draw = classification_metrics(truth[accepted], predicted[accepted], draw_weights[accepted])
        draws["macro_f1"].append(raw_draw["macro_f1"])
        for label in ("positive", "negative"):
            draws[f"{label}_precision"].append(accepted_draw["classes"][label]["precision"])
    intervals = {key: np.quantile(values, [0.025, 0.975]).tolist() for key, values in draws.items()}
    return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "raw": raw, "accepted": selective,
            "target_precision": target_precision, "target_recall": target_recall, "coverage": coverage,
            "by_target_group": groups, "validation_ci_95_by_video": intervals, "general_sentiment_baseline": baseline,
            "test_comments": len(gold), "test_pairs": len(pairs), "thresholds_fixed_before_test": True}


def require_test_calibration(settings: dict, run: Path) -> None:
    """Reject a known-impossible selective test using development artifacts only."""
    folder = run / "model"
    manifest = json.loads((folder / "training_manifest.json").read_text())
    path = folder / "calibration.json"
    expected = manifest.get("checkpoint_hashes", {}).get("calibration.json")
    if not expected or sha256(path) != expected:
        raise ValueError("La calibración no coincide con el entrenamiento; la prueba final permanece cerrada")
    calibration = json.loads(path.read_text())
    if calibration.get("precision_target") != settings["quality"]["valence_precision"]:
        raise ValueError("El criterio de calibración cambió; la prueba final permanece cerrada")
    thresholds = calibration.get("thresholds", {})
    disabled = [label for label in ("positive", "negative")
                if type(thresholds.get(label)) not in (int, float) or not 0 <= thresholds[label] <= 1]
    if disabled:
        raise ValueError("Calibración insuficiente en validación para " + ", ".join(disabled)
                         + ": no admite predicciones aceptadas de esas clases. La prueba final permanece cerrada")


def evaluate(settings: dict, run: Path) -> None:
    folder = run / "model"
    if (folder / "test_opened.json").exists():
        raise ValueError("La prueba final ya fue abierta. No ajustar ni reutilizarla como una prueba nueva.")
    training_manifest = json.loads((folder / "training_manifest.json").read_text())
    if training_manifest["gold_sha256"] != sha256(run / "annotations" / "gold.csv"):
        raise ValueError("Las anotaciones no corresponden al estudio de estos checkpoints")
    require_test_calibration(settings, run)
    pairs = read_csv(run / "training_pairs.csv")
    test = pairs.loc[pairs.split.eq("test")].copy()
    if test.empty:
        raise ValueError("Sin pares de prueba")
    _gpu()  # Do not consume a blind test on a machine that cannot execute it.
    atomic_json(folder / "test_opened.json", {"opened_at": stamp(), "calibration_sha256": sha256(folder / "calibration.json")})
    predictions = ensemble_predict(settings, run, test)
    gold = read_csv(run / "annotations" / "gold.csv")
    gold = gold.loc[gold.split.eq("test")]
    report = evaluation_report(settings, gold, test, predictions)
    predictions.to_csv(folder / "test_predictions.csv", index=False)
    atomic_json(folder / "evaluation.json", {**report, "created_at": stamp(), "quality_criteria": settings["quality"],
                "annotation_protocol": training_manifest.get("annotation_protocol", "two_independent_humans"),
                "annotation_limitation": training_manifest.get("annotation_limitation"),
                "method_version": training_manifest.get("method_version", "targeted-v1"),
                "annotation_lineage_sha256": training_manifest.get("annotation_lineage_sha256"),
                "sampling_probability_scope": training_manifest.get("sampling_probability_scope"),
                "gold_sha256": sha256(run / "annotations" / "gold.csv"),
                "training_manifest_sha256": sha256(folder / "training_manifest.json"), "test_predictions_sha256": sha256(folder / "test_predictions.csv")})
    if report["status"] != "passed":
        raise ValueError("El modelo no alcanzó los criterios fijados. No ejecutar inferencia de producción; hace falta corregir y obtener una prueba independiente.")


def infer_targets(settings: dict, run: Path) -> None:
    evaluation = json.loads((run / "model" / "evaluation.json").read_text())
    if evaluation.get("status") != "passed" or evaluation["training_manifest_sha256"] != sha256(run / "model" / "training_manifest.json"):
        raise ValueError("Se requiere prueba humana final superada para estos checkpoints")
    if evaluation.get("quality_criteria") != settings["quality"]:
        raise ValueError("Los criterios actuales no coinciden con los de la prueba final")
    gold = run / "annotations/gold.csv"
    if gold.exists() and evaluation.get("gold_sha256") != sha256(gold):
        raise ValueError("Las anotaciones cambiaron después de la prueba final")
    destination = run / "predictions.csv"
    if destination.exists():
        raise FileExistsError("Ya existen predicciones; crea otra ejecución para no reemplazarlas")
    from .registry import candidates
    frame = candidates(settings, run)
    # Main and panel remain identifiable; only main enters primary inference.
    result = ensemble_predict(settings, run, frame)
    result.to_csv(destination, index=False)
    atomic_json(run / "prediction_manifest.json", {"created_at": stamp(), "predictions_sha256": sha256(destination),
        "corpus_main_sha256": sha256(run / "corpus_main.csv"), "registry_sha256": sha256(settings["registry"]),
        "evaluation_sha256": sha256(run / "model" / "evaluation.json"), "rows": len(result)})
