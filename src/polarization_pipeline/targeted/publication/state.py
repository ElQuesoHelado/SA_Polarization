from __future__ import annotations

import csv
import hashlib
import json
import re
import tomllib
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from ..common import ROOT, atomic_json, config, read_csv, sha256, stamp

PROTOCOL = "targeted-publication-v1"


def load(path="config/targeted_publication.toml"):
    path = Path(path)
    path = path if path.is_absolute() else ROOT / path
    plan = tomllib.loads(path.read_text())
    if plan.get("protocol") != PROTOCOL:
        raise ValueError("Protocolo de publicación incompatible")
    settings = config(plan["parent_config"])
    parent = settings["workspace"] / plan["parent_run"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", plan["study_id"]):
        raise ValueError("study_id inválido")
    study = settings["workspace"] / plan["study_id"]
    if study.resolve() == parent.resolve():
        raise ValueError("El estudio debe estar aislado del padre")
    registry = Path(plan["registry"])
    registry = registry if registry.is_absolute() else ROOT / registry
    return settings, plan, parent, study, registry


def metadata_exclusions(settings, parent):
    """Only sampling metadata: never read/decode annotation payloads."""
    paths = [parent / "annotations/sampling_manifest.csv"]
    original = settings["workspace"] / "targeted_20261114/annotations/sampling_manifest.csv"
    if original.exists():
        paths.append(original)
    paths.extend(sorted((parent / "experiments").glob("*/sample.csv")))
    from ..annotations import text_key
    seen_videos, seen_texts, test_videos, test_ids = set(), set(), set(), set()
    hashes = {}
    for path in paths:
        hashes[str(path.resolve())] = sha256(path)
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                seen_videos.add(row["post_id"])
                seen_texts.add(text_key(row["text"]))
                if path == paths[0] and row.get("split") == "test":
                    test_videos.add(row["post_id"])
                    test_ids.add(row["comment_id"])
    return dict(seen_videos=seen_videos, seen_texts=seen_texts,
                test_videos=test_videos, test_ids=test_ids, hashes=hashes)


def verify(study, *, frozen=False):
    manifest = json.loads((study / "study.json").read_text())
    for path, expected in manifest["inputs"].items():
        if sha256(Path(path)) != expected:
            raise ValueError(f"Entrada protegida alterada: {Path(path).name}")
    if manifest.get("test_marker") and Path(manifest["test_marker"]).exists():
        raise ValueError("La prueba reservada del padre fue abierta")
    if frozen:
        snapshot = json.loads((study / "freeze.json").read_text())
        for name, expected in snapshot["files"].items():
            if sha256(study / name) != expected:
                raise ValueError(f"Snapshot alterado: {name}")
    return manifest


def seal(folder, names, filename="manifest.json", **extra):
    atomic_json(folder / filename, dict(created_at=stamp(), files={name: sha256(folder / name) for name in names}, **extra))


def verify_seal(folder, filename="manifest.json"):
    manifest = json.loads((folder / filename).read_text())
    for name, expected in manifest["files"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256(path) != expected:
            raise ValueError("Artefacto sellado alterado")
    return manifest


def output(settings, study):
    extension = study if (study / 'extension.json').exists() else study.parent
    if (extension / 'extension.json').exists():
        source = json.loads((extension / 'extension.json').read_text())
        path = settings['outputs'] / Path(source['source_study']).name / 'model_experiments' / extension.name
    else:
        path = settings["outputs"] / study.name
    path.mkdir(parents=True, exist_ok=True)
    return path


def sid(study, comment_id):
    return hashlib.sha256(f"{study.name}:{comment_id}".encode()).hexdigest()[:24]


@contextmanager
def lock(path):
    """OS lock: stale process death releases it; shared with publication captures."""
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
