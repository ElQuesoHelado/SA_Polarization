from __future__ import annotations

import hashlib
import json
import os
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
LABELS = ("positive", "negative", "neutral", "mixed", "not_evaluable")
POLITICAL = ("izquierda", "derecha")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".targeted-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(name, path)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def config(path: str | Path = "config/targeted.toml") -> dict:
    path = Path(path)
    path = path if path.is_absolute() else ROOT / path
    with path.open("rb") as handle:
        result = tomllib.load(handle)
    result["_root"] = ROOT
    result["_config_path"] = path
    for key in ("source_config", "input_csv", "workspace", "outputs", "registry"):
        item = Path(result[key])
        result[key] = item if item.is_absolute() else ROOT / item
    with result["source_config"].open("rb") as handle:
        result["source"] = tomllib.load(handle)
    return result


def fingerprint(settings: dict) -> str:
    return hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()


def run_directory(settings: dict, run_id: str, *, create: bool = False) -> Path:
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in run_id):
        raise ValueError("run-id solo admite letras, números, guiones y guiones bajos")
    path = settings["workspace"] / run_id
    if create:
        path.mkdir(parents=True, exist_ok=False)
    elif not path.is_dir():
        raise FileNotFoundError(f"No existe {path}; ejecuta targeted audit")
    return path


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, dtype=str, **kwargs)


def in_window(values: pd.Series, periods: dict) -> pd.Series:
    dates = pd.to_datetime(values, errors="coerce", utc=True)
    valid = pd.Series(False, index=values.index)
    for start, end in periods.values():
        valid |= dates.between(pd.Timestamp(start), pd.Timestamp(end))
    return valid


def stages(values: pd.Series, periods: dict) -> pd.Series:
    dates = pd.to_datetime(values, errors="coerce", utc=True)
    result = pd.Series("", index=values.index)
    for name, (start, end) in periods.items():
        result.loc[dates.between(pd.Timestamp(start), pd.Timestamp(end))] = name
    return result


def require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Faltan columnas: {', '.join(sorted(missing))}")
