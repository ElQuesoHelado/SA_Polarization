"""GPU inference entrypoint for Kaggle Kernels."""

from __future__ import annotations

import json
import shutil
import tempfile
import unicodedata
from pathlib import Path

import pandas as pd
import torch
from huggingface_hub import snapshot_download
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline


MODEL_ID = "pyupeu/robertuito-peruvian-sentiment"
BATCH_SIZE = 32
INPUT_NAME = "comentarios_consolidado.csv"
LABELS = {"LABEL_0": "negative", "LABEL_1": "neutral", "LABEL_2": "positive"}


def find_input() -> Path:
    matches = list(Path("/kaggle/input").rglob(INPUT_NAME))
    if not matches:
        raise FileNotFoundError(f"No se encontró {INPUT_NAME} en /kaggle/input; revisa el dataset source del kernel.")
    return matches[0]


def prepare_tokenizer_files(model_dir: Path) -> None:
    """Keep the tokenizer de-duplication workaround used in the source notebook."""
    def normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text.lower())
        return "".join(char for char in normalized if unicodedata.category(char) != "Mn")

    tokenizer_path = model_dir / "tokenizer.json"
    tokenizer_data = json.loads(tokenizer_path.read_text(encoding="utf-8"))
    added_tokens = tokenizer_data["added_tokens"]
    ordered = sorted(added_tokens, key=lambda token: (not token.get("special", False), token["id"]))
    seen, deduplicated = set(), []
    for token in ordered:
        normalized = normalize(token["content"])
        if normalized not in seen:
            seen.add(normalized)
            deduplicated.append(token)
    deduplicated.sort(key=lambda token: token["id"])
    tokenizer_data["added_tokens"] = deduplicated
    tokenizer_path.write_text(json.dumps(tokenizer_data, ensure_ascii=False), encoding="utf-8")

    config_path = model_dir / "tokenizer_config.json"
    tokenizer_config = json.loads(config_path.read_text(encoding="utf-8"))
    kept_ids = {token["id"] for token in deduplicated}
    decoder = tokenizer_config.get("added_tokens_decoder", {})
    tokenizer_config["added_tokens_decoder"] = {
        key: value for key, value in decoder.items() if int(key) in kept_ids
    }
    config_path.write_text(json.dumps(tokenizer_config, ensure_ascii=False), encoding="utf-8")


def load_tokenizer(model_dir: Path):
    # Work on tokenizer/config files only, keeping the Hugging Face cache intact.
    ignored = shutil.ignore_patterns(
        "*.safetensors", "*.bin", "*.h5", "*.msgpack", "*.onnx", "*.tflite", "*.pt"
    )
    with tempfile.TemporaryDirectory(prefix="sa-polarization-tokenizer-") as temp:
        writable_dir = Path(temp) / "model"
        shutil.copytree(model_dir, writable_dir, ignore=ignored)
        prepare_tokenizer_files(writable_dir)
        return AutoTokenizer.from_pretrained(writable_dir)


def main() -> None:
    source = find_input()
    frame = pd.read_csv(source)
    if "text" not in frame.columns:
        raise ValueError(f"El CSV {source} no contiene la columna text.")
    texts = frame["text"].fillna("").astype(str).tolist()
    model_dir = Path(snapshot_download(MODEL_ID))
    tokenizer = load_tokenizer(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    if not torch.cuda.is_available():
        raise RuntimeError("Este kernel requiere una GPU activa en Kaggle.")
    device = 0
    classifier = pipeline("text-classification", model=model, tokenizer=tokenizer, device=device)
    predictions = classifier(texts, batch_size=BATCH_SIZE, truncation=True) if texts else []
    frame["sentimiento"] = [LABELS.get(item["label"], item["label"]) for item in predictions]
    frame["confianza"] = [item["score"] for item in predictions]
    destination = Path("/kaggle/working/datos_clasificados.csv")
    frame.to_csv(destination, index=False)
    print(f"Clasificados {len(frame)} comentarios: {destination}")


if __name__ == "__main__":
    main()
