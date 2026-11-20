from __future__ import annotations

import json
import re
import unicodedata
import hashlib
from pathlib import Path

import pandas as pd

from .common import POLITICAL, read_csv, sha256


def normalized(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(char))


def load_registry(path: Path, *, frozen: bool = False) -> dict:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1:
        raise ValueError("Versión de registro de objetivos no soportada")
    matching = registry.get("matching", {})
    if matching and (matching.get("version") != 2 or any(matching.get(key, True) is not True for key in ("flexible_whitespace", "longest_mention"))):
        raise ValueError("Versión de coincidencias no soportada")
    if frozen and registry.get("status") != "reviewed":
        raise ValueError("El registro debe tener status=reviewed tras auditar actores, alias y fuentes")
    ids, aliases, annotation_ids = set(), {}, set()
    for target in registry["targets"]:
        if target["target_id"] in ids:
            raise ValueError("target_id duplicado")
        ids.add(target["target_id"])
        for identifier in target.get("annotation_ids", []):
            if identifier in annotation_ids:
                raise ValueError("Identificador de anotación compartido por distintos actores")
            annotation_ids.add(identifier)
        if target["target_group"] not in (*POLITICAL, "unknown", "not_political"):
            raise ValueError("Bloque de objetivo no soportado")
        if target["target_group"] in POLITICAL and not target.get("sources"):
            raise ValueError(f"Falta fuente citable para {target['target_id']}")
        if not target["aliases"]:
            raise ValueError("Objetivo sin alias: mantenerlo en la cola de revisión")
        for alias in target["aliases"]:
            alias = normalized(" ".join(alias.split()) if matching else alias)
            if not alias.strip() or (alias in aliases and aliases[alias] != target["target_id"]):
                raise ValueError("Alias vacío o compartido por distintos actores")
            aliases[alias] = target["target_id"]
    for target in registry["targets"]:
        if (set(target.get("annotation_ids", [])) & ids) - {target["target_id"]}:
            raise ValueError("Una transformación de identidad invade otro target_id")
    return registry


def registry_fingerprint(path: Path) -> str:
    """Administrative review status can change without changing the frozen target definitions."""
    registry = load_registry(path)
    content = {key: registry[key] for key in ("schema_version", "version", "targets")}
    if "matching" in registry:
        content["matching"] = registry["matching"]
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Matcher:
    def __init__(self, registry: dict):
        self.targets = {target["target_id"]: target for target in registry["targets"]}
        self.matching = registry.get("matching", {})
        if self.matching:
            self.alias_targets = {normalized(" ".join(alias.split())): target for target in registry["targets"] for alias in target["aliases"]}
            expressions = [re.escape(alias).replace(r"\ ", r"\s+") for alias in sorted(self.alias_targets, key=len, reverse=True)]
            self.combined = re.compile(r"(?<!\w)(?:" + "|".join(expressions) + r")(?!\w)")
        self.patterns = [(target, re.compile(r"(?<!\w)(?:" + "|".join(re.escape(normalized(alias)) for alias in sorted(target["aliases"], key=len, reverse=True)) + r")(?!\w)")) for target in registry["targets"]]

    def find(self, text: str, date: str = "") -> list[dict]:
        text_normalized = normalized(text)
        offsets = None
        if len(text_normalized) != len(text):
            offsets = [i for i, char in enumerate(text) for _ in normalized(char)]
        found = []
        if self.matching:
            usernames = list(re.finditer(r"@[\w.\-]+", text_normalized)) if self.matching.get("ignore_usernames") else []
            seen = set()
            for match in self.combined.finditer(text_normalized):
                if any(user.start() <= match.start() < user.end() for user in usernames):
                    continue
                target = self.alias_targets[" ".join(match.group().split())]
                if target["target_id"] in seen or (date and not target["valid_from"] <= date[:10] <= target["valid_to"]):
                    continue
                seen.add(target["target_id"])
                end = offsets[match.end() - 1] + 1 if offsets is not None else match.end()
                while end < len(text) and unicodedata.combining(text[end]):
                    end += 1
                found.append({"target_id": target["target_id"], "target_name": target["name"],
                    "target_group": target["target_group"], "entity_type": target["entity_type"],
                    "mention_start": offsets[match.start()] if offsets is not None else match.start(),
                    "mention_end": end,
                    "candidate_origin": "explicit_alias"})
            return found
        for target, pattern in self.patterns:
            if date and not target["valid_from"] <= date[:10] <= target["valid_to"]:
                continue
            matches = list(pattern.finditer(text_normalized))
            if matches:
                found.append({
                    "target_id": target["target_id"], "target_name": target["name"],
                    "target_group": target["target_group"], "entity_type": target["entity_type"],
                    "mention_start": offsets[matches[0].start()] if offsets is not None else matches[0].start(),
                    "mention_end": offsets[matches[0].end() - 1] + 1 if offsets is not None else matches[0].end(),
                    "candidate_origin": "explicit_alias",
                })
        return found


def candidates(settings: dict, run: Path) -> pd.DataFrame:
    registry = load_registry(settings["registry"])
    matcher = Matcher(registry)
    rows = []
    for name in ("corpus_main.csv", "corpus_panel.csv"):
        path = run / name
        if not path.exists():
            continue
        frame = read_csv(path)
        for values in frame.itertuples(index=False, name=None):
            row = dict(zip(frame.columns, values))
            for match in matcher.find(row["text"], row["comment_published_at"]):
                rows.append({**row, **match})
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("Sin candidatos explícitos; verifica metadatos y registro")
    result = result.drop_duplicates(["comment_id", "target_id", "corpus"])
    result.to_csv(run / "candidates.csv", index=False)
    from .common import atomic_json
    atomic_json(run / "candidate_manifest.json", {"registry_sha256": sha256(settings["registry"]), "rows": len(result), "origin": "explicit_alias"})
    return result


def discover(settings: dict, run: Path, *, use_ner: bool = False) -> None:
    """Produce a review queue, never assign blocks automatically to NER discoveries."""
    frame = read_csv(run / "corpus_main.csv")
    matcher = Matcher(load_registry(settings["registry"]))
    matched = candidates(settings, run)
    frequencies = matched.target_id.value_counts()
    queue = []
    if use_ner:
        from transformers import pipeline
        tagger = pipeline("token-classification", model=settings["ner_model"], aggregation_strategy="simple")
        sample = frame.sample(n=min(5000, len(frame)), random_state=settings["seed"])
        for row in sample.to_dict("records"):
            for entity in tagger(row["text"]):
                if entity["entity_group"] in ("PER", "ORG"):
                    queue.append({"name": row["text"][entity["start"]:entity["end"]], "origin": "ner", "count": 1, "target_group": "unknown"})
    for target in matcher.targets.values():
        queue.append({"name": target["name"], "origin": "registry", "count": int(frequencies.get(target["target_id"], 0)), "target_group": target["target_group"]})
    pd.DataFrame(queue).groupby(["name", "origin", "target_group"], as_index=False)["count"].sum().sort_values("count", ascending=False).to_csv(run / "target_review_queue.csv", index=False)
