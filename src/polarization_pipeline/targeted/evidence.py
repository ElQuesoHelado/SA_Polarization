"""Separate audited contextual references without changing human decisions or the sample."""
from __future__ import annotations

import json
from pathlib import Path

from .common import read_csv, sha256


def policy_sha(run: Path) -> str | None:
    path = run / "annotations" / "evidence_policy.json"
    return sha256(path) if path.exists() else None


def separate_evidence(run: Path, decisions: dict) -> tuple[dict, dict]:
    path = run / "annotations" / "evidence_policy.json"
    overrides = set()
    if path.exists():
        policy = json.loads(path.read_text())
        if policy.get("schema_version") != 1 or policy.get("main") != "explicit_only":
            raise ValueError("Política de evidencia no soportada")
        if policy.get("sampling_sha256") != sha256(path.parent / "sampling_manifest.csv"):
            raise ValueError("La política de evidencia corresponde a otra muestra")
        sample_ids = set(read_csv(path.parent / "sampling_manifest.csv").sample_id)
        for item in policy["contextual_targets"]:
            key = (item["sample_id"], item["target_id"])
            if key in overrides or key[0] not in sample_ids or not item.get("reason", "").strip():
                raise ValueError("Referencia contextual duplicada, desconocida o sin justificación")
            if key[0] in decisions and key[1] not in {x["target_id"] for x in decisions[key[0]]}:
                raise ValueError("La decisión humana cambió; volver a auditar la referencia contextual")
            overrides.add(key)
    primary, contextual = {}, {}
    for sample_id, items in decisions.items():
        primary[sample_id] = [x for x in items if (sample_id, x["target_id"]) not in overrides]
        contextual[sample_id] = [x for x in items if (sample_id, x["target_id"]) in overrides]
    return primary, contextual
