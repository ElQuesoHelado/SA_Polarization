from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "pipeline.toml"


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    with config_path.open("rb") as stream:
        config = tomllib.load(stream)
    config["_root"] = ROOT
    config["_config_path"] = config_path
    for section in ("paths",):
        for key, value in config.get(section, {}).items():
            candidate = Path(value)
            config[section][key] = candidate if candidate.is_absolute() else ROOT / candidate
    return config


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Falta la variable {name}; configúrala en .env o en el entorno.")
    return value
