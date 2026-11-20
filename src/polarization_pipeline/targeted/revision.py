"""Versioned resampling and verifiable reuse of genuine human decisions."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from .common import atomic_json, read_csv, sha256, stamp
from .registry import Matcher, load_registry, registry_fingerprint


def translate_items(items: list, registry: dict) -> list:
    """Only explicit identity mappings; no fuzzy names, political or valence inference."""
    mapping = {identifier: target["target_id"] for target in registry["targets"]
               for identifier in [target["target_id"], *target.get("annotation_ids", [])]}
    return [{**item, "target_id": mapping.get(item["target_id"], item["target_id"])} for item in items]


def registry_audit(settings: dict, source: Path, source_settings: dict) -> dict:
    from .assisted import review_records
    sample, _, decisions, _ = review_records(source_settings, source, pilot_only=False, require_reviewed=False)
    from .evidence import separate_evidence
    decisions, _ = separate_evidence(source, decisions)
    registry = load_registry(settings["registry"])
    matcher = Matcher(registry)
    results = {}
    for split in ("train", "validation"):
        selected = sample.loc[sample.split.eq(split)]
        tp = fp = fn = 0.0
        for row in selected.to_dict("records"):
            gold = {item["target_id"] for item in translate_items(decisions[row["sample_id"]], registry)}
            found = {item["target_id"] for item in matcher.find(row["text"], row["comment_published_at"])}
            weight = 1 / float(row["sampling_probability"])
            tp += weight * len(gold & found)
            fp += weight * len(found - gold)
            fn += weight * len(gold - found)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        results[split] = {"comments": len(selected), "precision": precision, "recall": recall,
                         "passed": precision >= settings["quality"]["target_precision"] and recall >= settings["quality"]["target_recall"]}
    return {"created_at": stamp(), "status": "passed" if all(x["passed"] for x in results.values()) else "failed",
            "development_only": True, "independent_evaluation": False, "splits": results,
            "source_sampling_sha256": sha256(source / "annotations/sampling_manifest.csv"),
            "source_human_sha256": sha256(source / "annotations/human_review.csv"),
            "candidate_registry_sha256": sha256(settings["registry"]), "quality": settings["quality"]}


def reusable(row: dict, original: dict, items: list, registry: dict) -> tuple[list, str]:
    for key in ("comment_id", "post_id", "text", "parent_text", "post_title", "comment_published_at"):
        if row.get(key, "") != original.get(key, ""):
            return [], "text_or_context_changed"
    translated = translate_items(items, registry)
    ids = [x["target_id"] for x in translated]
    if len(set(ids)) != len(ids):
        return [], "identity_mapping_collision"
    matcher = Matcher(registry)
    found = {x["target_id"] for x in matcher.find(row["text"], row["comment_published_at"])}
    for item in translated:
        snippet = row["text"][item["mention_start"]:item["mention_end"]]
        explicit = {x["target_id"] for x in matcher.find(snippet, row["comment_published_at"])}
        if item["target_id"] not in explicit:
            return [], "unmapped_or_contextual_identity"
    if found - set(ids):
        return [], "new_candidate_requires_human_check"
    return translated, "compatible"


def load_inherited(settings: dict, run: Path, sample: pd.DataFrame) -> dict:
    from .assisted import review_records
    folder = run / "annotations"
    manifest = json.loads((folder / "manifest.json").read_text())
    expected = manifest.get("inheritance_sha256")
    path = folder / "inheritance_manifest.json"
    if not expected:
        if path.exists() or (folder / "inherited_reviews.csv").exists():
            raise ValueError("Herencia sin manifiesto de integridad")
        return {}
    if not path.exists() or sha256(path) != expected:
        raise ValueError("El manifiesto de herencia cambió")
    meta = json.loads(path.read_text())
    if meta["registry_sha256"] != registry_fingerprint(settings["registry"]):
        raise ValueError("Registro distinto al de las revisiones heredadas")
    for name, digest in meta["files"].items():
        source = (run / name).resolve()
        if not source.is_relative_to(run.resolve()) or not source.exists() or sha256(source) != digest:
            raise ValueError("Una fuente de revisión heredada cambió")
    snapshot = run / "inheritance_source"
    source_sample, _, decisions, _ = review_records({"registry": snapshot / "registry.json"}, snapshot,
        pilot_only=False, require_reviewed=False)
    from .evidence import separate_evidence
    _, source_contextual = separate_evidence(snapshot, decisions)
    originals = source_sample.set_index("sample_id").to_dict("index")
    previous_videos = set(source_sample.post_id)
    from .annotations import text_key
    previous_texts = {text_key(x) for x in source_sample.text}
    test = sample.loc[sample.split.eq("test")]
    if set(test.post_id) & previous_videos or any(text_key(x) in previous_texts for x in test.text):
        raise ValueError("La nueva prueba contiene videos o textos revisados anteriormente")
    inherited = read_csv(folder / "inherited_reviews.csv")
    if inherited.sample_id.duplicated().any() or not set(inherited.sample_id) <= set(sample.sample_id):
        raise ValueError("IDs heredados duplicados o ajenos")
    current = sample.set_index("sample_id").to_dict("index")
    registry = load_registry(settings["registry"])
    result = {}
    for item in inherited.to_dict("records"):
        key = item["sample_id"]
        row = current[key]
        if row["split"] == "test" or key not in originals:
            raise ValueError("No se pueden heredar etiquetas de prueba ni IDs desconocidos")
        if source_contextual[key]:
            raise ValueError("No heredar evidencia contextual como referencia explícita")
        translated, reason = reusable(row, originals[key], decisions[key], registry)
        if reason != "compatible" or translated != json.loads(item["annotation_json"]):
            raise ValueError("La anotación heredada difiere de la decisión humana de origen")
        result[key] = translated
    return result


def revise(settings: dict, destination: Path, source: Path, source_settings: dict) -> dict:
    """Create a new run only after a development audit; never edit the source run."""
    from .annotations import export_annotations
    from .assisted import initialize, review_records, save_csv
    if destination.exists():
        raise FileExistsError("La ejecución derivada ya existe; no se sobrescribe")
    if (source / "model/test_opened.json").exists():
        raise ValueError("Esta migración requiere una prueba original no consumida")
    registry = load_registry(settings["registry"], frozen=True)
    audit = registry_audit(settings, source, source_settings)
    if audit["status"] != "passed":
        raise ValueError("El extractor revisado no supera precisión/recall en desarrollo; no pedir otra anotación")
    sample, _, decisions, counts = review_records(source_settings, source, pilot_only=False, require_reviewed=False)
    from .evidence import separate_evidence
    _, source_contextual = separate_evidence(source, decisions)
    # Verify all input hashes before copying or creating the new sample.
    source_manifest = json.loads((source / "annotations/manifest.json").read_text())
    if source_manifest.get("corpus_main_sha256") != sha256(source / "corpus_main.csv"):
        raise ValueError("El corpus original cambió después del muestreo")
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("corpus_main.csv", "corpus_panel.csv"):
        if (source / name).exists():
            shutil.copy2(source / name, destination / name)
    snapshot = destination / "inheritance_source"
    (snapshot / "annotations").mkdir(parents=True)
    for name in ("sampling_manifest.csv", "human_review.csv", "ai_proposals.csv", "manifest.json", "assisted_manifest.json", "evidence_policy.json", "inheritance_manifest.json", "inherited_reviews.csv"):
        if (source / "annotations" / name).exists():
            shutil.copy2(source / "annotations" / name, snapshot / "annotations" / name)
    if (source / "inheritance_source").is_dir():
        shutil.copytree(source / "inheritance_source", snapshot / "inheritance_source")
    shutil.copy2(source_settings["registry"], snapshot / "registry.json")
    export_annotations(settings, destination, exclude_test_sample=sample)
    initialize(settings, destination)
    folder = destination / "annotations"
    current = read_csv(folder / "sampling_manifest.csv")
    originals = sample.set_index("sample_id").to_dict("index")
    inherited, pending = [], []
    for row in current.to_dict("records"):
        key = row["sample_id"]
        if row["split"] != "test" and key in originals:
            if source_contextual[key]:
                translated, reason = [], "source_contextual_evidence"
            else:
                translated, reason = reusable(row, originals[key], decisions[key], registry)
            if reason == "compatible":
                inherited.append({"sample_id": key, "annotation_json": json.dumps(translated, ensure_ascii=False),
                                  "source_sample_id": key, "source_run": source.name})
                continue
        else:
            reason = "new_comment"
        pending.append({"sample_id": key, "reason": reason, "previously_reviewed": key in originals})
    save_csv(pd.DataFrame(inherited, columns=["sample_id", "annotation_json", "source_sample_id", "source_run"]), folder / "inherited_reviews.csv")
    save_csv(pd.DataFrame(pending), folder / "pending_review.csv")
    files = {p.relative_to(destination).as_posix(): sha256(p) for p in snapshot.rglob("*") if p.is_file()}
    files["annotations/inherited_reviews.csv"] = sha256(folder / "inherited_reviews.csv")
    atomic_json(folder / "inheritance_manifest.json", {"source_run": source.name, "created_at": stamp(),
        "registry_sha256": registry_fingerprint(settings["registry"]), "files": files,
        "original_test_retired_without_evaluation": True,
        "confirmation": "Decisiones humanas originales verificadas; no se crean confirmaciones en human_review.csv."})
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["inheritance_sha256"] = sha256(folder / "inheritance_manifest.json")
    atomic_json(folder / "manifest.json", manifest)
    report = {"created_at": stamp(), "source_run": source.name, "source_comments": len(sample), "source_decisions": counts,
        "sample_comments": len(current), "inherited": len(inherited), "pending": len(pending),
        "new_comments": sum(not x["previously_reviewed"] for x in pending),
        "previous_comments_requiring_check": sum(x["previously_reviewed"] for x in pending),
        "sampling_split_seed": settings.get("sampling_split_seed", settings["seed"]),
        "test_comments": int(current.split.eq("test").sum()), "test_previously_reviewed_videos": 0,
        "pending_reasons": pd.Series([x["reason"] for x in pending]).value_counts().to_dict(),
        "registry_audit": audit, "corpus_sha256": {n: sha256(destination / n) for n in ("corpus_main.csv", "corpus_panel.csv") if (destination / n).exists()}}
    atomic_json(destination / "revision_report.json", report)
    atomic_json(folder / "evidence_policy.json", {"schema_version": 1, "main": "explicit_only",
        "sampling_sha256": sha256(folder / "sampling_manifest.csv"), "contextual_targets": []})
    load_inherited(settings, destination, current)
    return report
