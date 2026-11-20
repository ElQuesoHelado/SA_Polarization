"""AI suggestions and explicit single-human review, kept separate from two-human annotation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from .annotations import parse_review, validate_items
from .common import atomic_json, read_csv, sha256, stamp
from .registry import load_registry, registry_fingerprint

PROTOCOL = "ai_assisted_single_human_v1"
LIMITATION = "Referencia de un único humano asistido por IA, incluida la prueba; sin acuerdo humano independiente."


def save_csv(frame: pd.DataFrame, path: Path) -> None:
    import os
    import tempfile
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".assisted-")
    os.close(fd)
    try:
        frame.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def annotation_digest(items: list) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def checked_sample(settings: dict, run: Path) -> tuple[pd.DataFrame, dict]:
    folder = run / "annotations"
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest["registry_sha256"] != registry_fingerprint(settings["registry"]):
        raise ValueError("El registro cambió; conservar esta ejecución y preparar otra muestra")
    if manifest["sampling_sha256"] != sha256(folder / "sampling_manifest.csv"):
        raise ValueError("El manifiesto de muestreo fue alterado")
    if manifest.get("annotation_protocol") != PROTOCOL:
        raise ValueError("Primero ejecutar assisted-init")
    return read_csv(folder / "sampling_manifest.csv"), manifest


def initialize(settings: dict, run: Path) -> Path:
    folder = run / "annotations"
    if (folder / "assisted_manifest.json").exists():
        raise FileExistsError("La revisión asistida ya existe; se reanuda, no se sobrescribe")
    if (folder / "gold.csv").exists() or (run / "model").exists():
        raise ValueError("No cambiar el protocolo de una muestra adjudicada o entrenada")
    original = json.loads((folder / "manifest.json").read_text())
    if original["registry_sha256"] != registry_fingerprint(settings["registry"]) or original["sampling_sha256"] != sha256(folder / "sampling_manifest.csv"):
        raise ValueError("El registro o muestreo cambió antes de iniciar")
    hashes = {}
    for number in (1, 2):
        path = folder / f"reviewer_{number}.csv"
        previous = read_csv(path)
        if previous.annotation_json.str.strip().ne("").any() or previous.review_complete.str.strip().ne("").any():
            raise ValueError("Hay revisiones previas; conservarlas y crear otra ejecución")
        hashes[path.name] = sha256(path)
    sample = read_csv(folder / "sampling_manifest.csv")
    human = sample.reindex(columns=["sample_id", "comment_id", "text", "parent_text", "post_title", "pilot"], fill_value="").copy()
    for column in ("annotation_json", "review_complete", "reviewed_at", "reviewer_id", "decision", "proposal_sha256"):
        human[column] = ""
    save_csv(human, folder / "human_review.csv")
    proposals = pd.DataFrame(columns=["sample_id", "comment_id", "text", "ai_annotation_json", "ai_note", "ai_origin", "proposed_at"])
    save_csv(proposals, folder / "ai_proposals.csv")
    atomic_json(folder / "assisted_manifest.json", {"protocol": PROTOCOL, "created_at": stamp(), "legacy_form_sha256": hashes,
        "proposal_sha256": sha256(folder / "ai_proposals.csv"), "batches": [], "limitation": LIMITATION})
    original.update(annotation_protocol=PROTOCOL, status="awaiting_assisted_human_review", annotation_limitation=LIMITATION)
    atomic_json(folder / "manifest.json", original)
    return folder / "human_review.csv"


def load_proposals(settings: dict, run: Path, sample: pd.DataFrame) -> pd.DataFrame:
    folder = run / "annotations"
    meta = json.loads((folder / "assisted_manifest.json").read_text())
    path = folder / "ai_proposals.csv"
    if sha256(path) != meta["proposal_sha256"]:
        raise ValueError("Las propuestas cambiaron fuera de assisted-proposals")
    frame = read_csv(path)
    if frame.sample_id.duplicated().any() or not set(frame.sample_id) <= set(sample.sample_id):
        raise ValueError("Propuestas duplicadas o ajenas a la muestra")
    expected = sample.set_index("sample_id")
    targets = {x["target_id"] for x in load_registry(settings["registry"])["targets"]}
    for row in frame.to_dict("records"):
        source = expected.loc[row["sample_id"]]
        if row["text"] != source.text or row["comment_id"] != source.comment_id:
            raise ValueError("Texto o identificador de propuesta alterado")
        validate_items(json.loads(row["ai_annotation_json"]), row["text"], targets)
        if not row["ai_origin"].strip() or not row["proposed_at"].strip():
            raise ValueError("Propuesta sin procedencia")
    return frame


def import_proposals(settings: dict, run: Path, path: Path) -> None:
    sample, manifest = checked_sample(settings, run)
    if manifest["status"] == "human_reviewed_assisted":
        raise ValueError("La revisión ya está cerrada")
    folder = run / "annotations"
    existing = load_proposals(settings, run, sample)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not str(payload.get("origin", "")).strip() or not isinstance(payload.get("proposals"), list):
        raise ValueError("Se requieren origin y proposals en el lote")
    indexed = sample.set_index("sample_id")
    targets = {x["target_id"] for x in load_registry(settings["registry"])["targets"]}
    seen = set(existing.sample_id)
    rows = []
    for item in payload["proposals"]:
        key = item["sample_id"]
        if key in seen or key not in indexed.index:
            raise ValueError("No sobrescribir propuestas; IDs duplicados o desconocidos")
        source = indexed.loc[key]
        annotations = validate_items(item["annotations"], source.text, targets)
        rows.append({"sample_id": key, "comment_id": source.comment_id, "text": source.text,
            "ai_annotation_json": json.dumps(annotations, ensure_ascii=False), "ai_note": item.get("note", ""),
            "ai_origin": payload["origin"], "proposed_at": stamp()})
        seen.add(key)
    if not rows:
        raise ValueError("Lote vacío")
    save_csv(pd.concat([existing, pd.DataFrame(rows)], ignore_index=True), folder / "ai_proposals.csv")
    meta = json.loads((folder / "assisted_manifest.json").read_text())
    meta["proposal_sha256"] = sha256(folder / "ai_proposals.csv")
    meta["batches"].append({"source_sha256": sha256(path), "rows": len(rows), "imported_at": stamp(), "origin": payload["origin"]})
    atomic_json(folder / "assisted_manifest.json", meta)


def review_records(settings: dict, run: Path, *, pilot_only: bool,
                   require_reviewed: bool = True) -> tuple[pd.DataFrame, dict, dict, dict]:
    sample, manifest = checked_sample(settings, run)
    proposals = load_proposals(settings, run, sample)
    from .revision import load_inherited
    inherited = load_inherited(settings, run, sample)
    if pilot_only:
        sample = sample.loc[sample.pilot.str.lower().eq("true")]
    local_sample = sample.loc[~sample.sample_id.isin(inherited)]
    if not set(local_sample.sample_id) <= set(proposals.sample_id):
        raise ValueError("Faltan propuestas para los comentarios a importar")
    folder = run / "annotations"
    targets = {x["target_id"] for x in load_registry(settings["registry"], frozen=require_reviewed and not pilot_only)["targets"]}
    decisions = parse_review(folder / "human_review.csv", local_sample, targets, allow_extra=True)
    human = read_csv(folder / "human_review.csv").set_index("sample_id")
    expected = read_csv(folder / "sampling_manifest.csv").set_index("sample_id")
    if human.index.duplicated().any() or set(human.index) != set(expected.index):
        raise ValueError("IDs humanos duplicados o ajenos a la muestra")
    for key, row in human.iterrows():
        if any(row.get(column, "") != expected.loc[key].get(column, "") for column in ("text", "comment_id", "parent_text", "post_title")):
            raise ValueError("Texto o contexto editado en formulario humano")
    proposed = proposals.set_index("sample_id")
    counts = {"accepted": 0, "modified": 0}
    selected_inherited = {key: items for key, items in inherited.items() if key in set(sample.sample_id)}
    if inherited:
        counts["inherited"] = len(selected_inherited)
        for key in selected_inherited:
            if human.loc[key].annotation_json.strip() or human.loc[key].review_complete.strip():
                raise ValueError("No crear confirmaciones locales para revisiones heredadas")
        decisions.update(selected_inherited)
    for key in sample.sample_id:
        if key in selected_inherited:
            continue
        row, suggestion = human.loc[key], proposed.loc[key]
        ai = validate_items(json.loads(suggestion.ai_annotation_json), row.text, targets)
        decision = "accepted" if decisions[key] == ai else "modified"
        if row.decision != decision or row.proposal_sha256 != annotation_digest(ai) or not row.reviewer_id.strip() or not row.reviewed_at.strip():
            raise ValueError("Falta confirmación humana con procedencia o cambió la propuesta")
        counts[decision] += 1
    return sample, manifest, decisions, counts


def check_review(settings: dict, run: Path) -> dict:
    """Read-only diagnostics, including incomplete runs and an unreviewed registry."""
    from .revision import load_inherited
    from .registry import Matcher
    sample, _ = checked_sample(settings, run)
    proposals = load_proposals(settings, run, sample)
    inherited = load_inherited(settings, run, sample)
    human = read_csv(run / "annotations/human_review.csv")
    if human.sample_id.duplicated().any() or set(human.sample_id) != set(sample.sample_id):
        raise ValueError("IDs humanos duplicados o ajenos")
    expected = sample.set_index("sample_id")
    for row in human.to_dict("records"):
        if any(row.get(column, "") != expected.loc[row["sample_id"]].get(column, "") for column in ("text", "comment_id", "parent_text", "post_title")):
            raise ValueError("Texto o contexto editado en formulario humano")
    completed = human.loc[human.review_complete.str.lower().isin(["true", "1", "yes", "si", "sí"])]
    targets = {x["target_id"] for x in load_registry(settings["registry"])["targets"]}
    parsed = parse_review(run / "annotations/human_review.csv", sample.loc[sample.sample_id.isin(completed.sample_id)], targets, allow_extra=True)
    indexed = proposals.set_index("sample_id")
    for row in completed.to_dict("records"):
        if row["sample_id"] not in indexed.index:
            raise ValueError("Confirmación sin propuesta")
        ai = json.loads(indexed.loc[row["sample_id"], "ai_annotation_json"])
        expected = "accepted" if parsed[row["sample_id"]] == ai else "modified"
        if row["decision"] != expected or row["proposal_sha256"] != annotation_digest(ai) or not row["reviewer_id"].strip() or not row["reviewed_at"].strip():
            raise ValueError("Confirmación humana sin procedencia válida")
    if set(parsed) & set(inherited):
        raise ValueError("Una revisión heredada fue confirmada otra vez sin migración")
    pending = set(sample.sample_id) - set(parsed) - set(inherited)
    registry = load_registry(settings["registry"])
    result = {"comments": len(sample), "human_confirmed_here": len(parsed), "inherited": len(inherited),
              "pending": len(pending), "pending_without_proposal": len(pending - set(proposals.sample_id)),
              "decisions": completed.decision.value_counts().to_dict(), "registry_status": registry["status"],
              "ready_to_import": not pending and registry["status"] == "reviewed", "test_opened": (run / "model/test_opened.json").exists()}
    # Never report extraction performance for the final-test partition here.
    matcher = Matcher(registry)
    diagnostics = {}
    all_decisions = {**inherited, **parsed}
    from .evidence import separate_evidence
    all_decisions, _ = separate_evidence(run, all_decisions)
    for split in ("train", "validation"):
        selected = sample.loc[sample.split.eq(split) & sample.sample_id.isin(all_decisions)]
        complete = len(selected) == int(sample.split.eq(split).sum())
        tp = fp = fn = 0.0
        for row in selected.to_dict("records"):
            gold = {x["target_id"] for x in all_decisions[row["sample_id"]]}
            found = {x["target_id"] for x in matcher.find(row["text"], row["comment_published_at"])}
            weight = 1 / float(row["sampling_probability"])
            tp += weight * len(gold & found); fp += weight * len(found - gold); fn += weight * len(gold - found)
        diagnostics[split] = {"reviewed_comments": len(selected), "complete": complete,
            "precision": tp / (tp + fp) if complete and tp + fp else None,
            "recall": tp / (tp + fn) if complete and tp + fn else None,
            "scope": "Desarrollo completo exclusivamente; no calcular sobre el subconjunto seleccionado por compatibilidad."}
    result["development_extraction"] = diagnostics
    return result


def import_review(settings: dict, run: Path, *, pilot_only: bool = False) -> None:
    if (run / "model").exists():
        raise ValueError("Ya hay un modelo; conservar la referencia utilizada para entrenar")
    sample, manifest, decisions, counts = review_records(settings, run, pilot_only=pilot_only)
    from .evidence import separate_evidence, policy_sha
    primary, contextual = separate_evidence(run, decisions)
    folder = run / "annotations"
    report = {"protocol": PROTOCOL, "reviewed_at": stamp(), "comments": len(sample), **counts,
        "limitation": LIMITATION, "interhuman_agreement": None, "human_review_sha256": sha256(folder / "human_review.csv"),
        "proposal_sha256": sha256(folder / "ai_proposals.csv")}
    if manifest.get("inheritance_sha256"):
        report["inheritance_sha256"] = manifest["inheritance_sha256"]
    report.update(evidence_policy_sha256=policy_sha(run),
        primary_annotation_units=sum(map(len, primary.values())),
        contextual_annotation_units=sum(map(len, contextual.values())),
        contextual_scope="Referencia separada para sensibilidad; no habilita resolución contextual en producción.")
    if pilot_only:
        atomic_json(folder / "assisted_pilot_report.json", report)
        print(f"Piloto confirmado: {counts}. No estima acuerdo entre humanos.")
        return
    if not (folder / "assisted_pilot_report.json").exists():
        raise ValueError("Primero importar el piloto asistido")
    gold = sample.copy()
    gold["annotation_json"] = [json.dumps(primary[key], ensure_ascii=False) for key in gold.sample_id]
    gold["annotation_protocol"] = PROTOCOL
    save_csv(gold, folder / "gold.csv")
    context = sample.copy()
    context["annotation_json"] = [json.dumps(contextual[key], ensure_ascii=False) for key in context.sample_id]
    save_csv(context, folder / "contextual_annotations.csv")
    report["contextual_sha256"] = sha256(folder / "contextual_annotations.csv")
    report["gold_sha256"] = sha256(folder / "gold.csv")
    atomic_json(folder / "assisted_review_report.json", report)
    manifest.update(status="human_reviewed_assisted", imported_at=stamp(), gold_sha256=report["gold_sha256"],
        assisted_report_sha256=sha256(folder / "assisted_review_report.json"))
    atomic_json(folder / "manifest.json", manifest)


def verify_completed(settings: dict, run: Path) -> None:
    folder = run / "annotations"
    manifest = json.loads((folder / "manifest.json").read_text())
    # Remote training receives an integrity-bound receipt instead of any final-test labels.
    receipt = folder / "assisted_training_receipt.json"
    if manifest.get("study_gold_sha256") and receipt.exists():
        report = json.loads(receipt.read_text())
        if (sha256(receipt) != manifest.get("assisted_receipt_sha256") or report.get("gold_sha256") != sha256(folder / "gold.csv")
                or report.get("study_gold_sha256") != manifest["study_gold_sha256"] or report.get("protocol") != PROTOCOL
                or report.get("source_review_report_sha256") != manifest.get("assisted_report_sha256")):
            raise ValueError("Recibo de revisión asistida inválido")
        return
    _, _, decisions, _ = review_records(settings, run, pilot_only=False)
    from .evidence import separate_evidence, policy_sha
    primary, _ = separate_evidence(run, decisions)
    report_path = folder / "assisted_review_report.json"
    if sha256(report_path) != manifest.get("assisted_report_sha256"):
        raise ValueError("El informe de revisión asistida cambió")
    report = json.loads(report_path.read_text())
    if report.get("inheritance_sha256") != manifest.get("inheritance_sha256"):
        raise ValueError("La herencia de revisión cambió tras importar")
    if report.get("evidence_policy_sha256") != policy_sha(run):
        raise ValueError("La política de evidencia cambió tras importar")
    if report.get("contextual_sha256") != sha256(folder / "contextual_annotations.csv"):
        raise ValueError("Las anotaciones contextuales cambiaron")
    if report["human_review_sha256"] != sha256(folder / "human_review.csv") or report["proposal_sha256"] != sha256(folder / "ai_proposals.csv"):
        raise ValueError("La revisión humana o propuestas cambiaron tras importar")
    if report["gold_sha256"] != sha256(folder / "gold.csv"):
        raise ValueError("Las anotaciones finales cambiaron")
    for row in read_csv(folder / "gold.csv").to_dict("records"):
        if json.loads(row["annotation_json"]) != primary[row["sample_id"]]:
            raise ValueError("Gold difiere de las decisiones humanas explícitas")
