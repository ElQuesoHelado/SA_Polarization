"""User-cohort pilot suggestions with explicit, separately recorded human decisions."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .annotations import validate_items
from .assisted import annotation_digest, save_csv
from .common import atomic_json, read_csv, require_columns, sha256, stamp
from .registry import load_registry

PROTOCOL = "targeted-user-cohort-assisted-pilot-v1"
HUMAN_COLUMNS = ("annotation_json", "review_complete", "reviewed_at", "reviewer_id", "decision", "proposal_sha256")


def locations(settings, run, cohort_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", cohort_id):
        raise ValueError("cohort-id inválido")
    root = run / "cohorts" / cohort_id
    report = settings["outputs"] / run.name / "cohorts" / cohort_id
    return root, report


def verify_design(settings, run, cohort_id):
    root, report = locations(settings, run, cohort_id)
    if (run / "model/test_opened.json").exists():
        raise ValueError("La prueba final debe permanecer reservada")
    manifest = json.loads((report / "manifest.json").read_text())
    summary = json.loads((report / "summary.json").read_text())
    if manifest["status"] != "complete" or summary["registry_sha256"] != sha256(settings["registry"]):
        raise ValueError("Cohorte incompleta o registro alterado")
    allowed = (root.resolve(), report.resolve())
    for name, digest in manifest["artifacts"].items():
        path = Path(name).resolve()
        if not any(path.is_relative_to(folder) for folder in allowed) or sha256(path) != digest:
            raise ValueError("Artefacto de diseño de cohorte alterado")
    if sha256(run / "annotations/gold.csv") != summary["human_gold_sha256"]:
        raise ValueError("Referencia original alterada")
    return root, report, summary


def initialize(settings, run, cohort_id, *, pilot_users=25):
    root, report, summary = verify_design(settings, run, cohort_id)
    folder = root / "annotations"
    if folder.exists():
        raise FileExistsError("El piloto ya está fijado; continuar sin regenerarlo")
    users = read_csv(root / "selected_users.csv")
    if not 0 < pilot_users < len(users):
        raise ValueError("Conservar usuarios pendientes fuera del piloto")
    pilot = set(users.iloc[:pilot_users].user_id)
    comments = read_csv(root / "comments.csv")
    sample = comments.loc[comments.user_id.isin(pilot)].sample(frac=1, random_state=57).reset_index(drop=True)
    remaining = comments.loc[~comments.user_id.isin(pilot)]
    folder.mkdir()
    sample.to_csv(folder / "pilot_sample.csv", index=False)
    remaining[["sample_id", "user_id", "comment_id", "post_id", "fold"]].to_csv(folder / "pending_ids.csv", index=False)
    form = sample[["sample_id", "comment_id", "text"]].copy()
    for key in HUMAN_COLUMNS:
        form[key] = ""
    save_csv(form, folder / "human_review.csv")
    atomic_json(folder / "ai_proposals.json", {})
    plan = {"protocol": PROTOCOL, "created_at": stamp(), "cohort_id": cohort_id,
        "pilot_users": pilot_users, "pilot_comments": len(sample), "pending_users": len(users) - pilot_users,
        "pending_comments": len(remaining), "shared_videos_pilot_pending": len(set(sample.post_id) & set(remaining.post_id)),
        "pilot_sample_sha256": sha256(folder / "pilot_sample.csv"), "pending_ids_sha256": sha256(folder / "pending_ids.csv"),
        "registry_sha256": summary["registry_sha256"], "design_manifest_sha256": sha256(report / "manifest.json"),
        "evidence_policy": "explicit_only", "training_allowed": False, "model_comparison_allowed_without_human_reference": False,
        "reference_protocol": "ai_assisted_single_human_v1", "limitation": "Un humano asistido por IA; sin acuerdo entre humanos. Las propuestas solas no validan el modelo ni AP.",
        "pending_scope": "Usuarios pendientes de anotación; no una prueba independiente automáticamente, pueden compartir videos con el piloto.",
        "outcomes_to_check_later": ["affinity_assignment", "paired_user_coverage", "AP_and_gap_error_and_sign", "block_valence_precision"],
        "frozen_settings": {key: settings[key] for key in ("seed", "minimum_positive_videos", "affinity_positive_share", "evaluation_min_interactions", "evaluation_min_videos", "quality")}}
    atomic_json(folder / "plan.json", plan)
    atomic_json(folder / "state.json", {"proposal_sha256": sha256(folder / "ai_proposals.json"), "plan_sha256": sha256(folder / "plan.json"), "status": "awaiting_ai_proposals", "batches": []})
    return folder


def checked(settings, run, cohort_id):
    root, report, _ = verify_design(settings, run, cohort_id)
    folder = root / "annotations"
    plan = json.loads((folder / "plan.json").read_text()); state = json.loads((folder / "state.json").read_text())
    if (plan["protocol"] != PROTOCOL or sha256(folder / "plan.json") != state["plan_sha256"]
        or sha256(report / "manifest.json") != plan["design_manifest_sha256"]
        or sha256(folder / "pilot_sample.csv") != plan["pilot_sample_sha256"]
        or sha256(folder / "pending_ids.csv") != plan["pending_ids_sha256"]
        or sha256(folder / "ai_proposals.json") != state["proposal_sha256"]
        or any(settings[key] != value for key, value in plan["frozen_settings"].items())):
        raise ValueError("Protocolo, muestra, propuestas o criterios alterados")
    return folder, read_csv(folder / "pilot_sample.csv"), plan, state


def import_proposals(settings, run, cohort_id, batch):
    folder, sample, plan, state = checked(settings, run, cohort_id)
    if (folder / "pilot_gold.csv").exists():
        raise ValueError("Referencia piloto cerrada")
    if batch.get("sample_sha256") != plan["pilot_sample_sha256"] or not batch.get("origin", "").strip() or not batch.get("proposals"):
        raise ValueError("Lote vacío, sin procedencia o de otra muestra")
    targets = {x["target_id"] for x in load_registry(settings["registry"])["targets"]}
    sample = sample.set_index("sample_id"); stored = json.loads((folder / "ai_proposals.json").read_text())
    for item in batch["proposals"]:
        sid = item["sample_id"]
        if sid not in sample.index or sid in stored or not item.get("note", "").strip():
            raise ValueError("Propuesta duplicada, ajena al piloto o sin explicación")
        annotations = validate_items(item["annotations"], sample.loc[sid].text, targets)
        stored[sid] = {"annotations": annotations, "note": item["note"], "origin": batch["origin"],
                       "human_confirmed": False, "proposed_at": stamp()}
    atomic_json(folder / "ai_proposals.json", stored)
    state.update(proposal_sha256=sha256(folder / "ai_proposals.json"), status="ai_proposals_complete" if len(stored) == len(sample) else "ai_proposals_partial")
    state["batches"].append({"rows": len(batch["proposals"]), "origin": batch["origin"], "imported_at": stamp()})
    atomic_json(folder / "state.json", state)
    return {"proposed": len(stored), "pilot_comments": len(sample), "human_confirmed": False}


def reference_status(settings, run, cohort_id):
    folder, sample, plan, _ = checked(settings, run, cohort_id)
    proposals = json.loads((folder / "ai_proposals.json").read_text())
    frame = read_csv(folder / "human_review.csv")
    require_columns(frame, ["sample_id", "comment_id", "text", *HUMAN_COLUMNS])
    if frame.sample_id.duplicated().any() or set(frame.sample_id) != set(sample.sample_id):
        raise ValueError("Formulario con IDs duplicados o ajenos")
    indexed = sample.set_index("sample_id"); targets = {x["target_id"] for x in load_registry(settings["registry"])["targets"]}
    confirmed = {}
    for row in frame.to_dict("records"):
        sid = row["sample_id"]
        if row["text"] != indexed.loc[sid].text or row["comment_id"] != indexed.loc[sid].comment_id:
            raise ValueError("Identidad o texto humano editados")
        if row["review_complete"].lower() not in ("true", "1", "yes", "si", "sí"):
            if any(row[key] for key in HUMAN_COLUMNS):
                raise ValueError("Decisión humana parcial inconsistente")
            continue
        if sid not in proposals or not row["reviewer_id"].strip() or not row["reviewed_at"].strip():
            raise ValueError("Confirmación humana sin procedencia")
        annotations = validate_items(json.loads(row["annotation_json"]), row["text"], targets)
        suggested = proposals[sid]["annotations"]
        expected = "accepted" if annotations == suggested else "modified"
        if row["decision"] != expected or row["proposal_sha256"] != annotation_digest(suggested):
            raise ValueError("Decisión humana incompatible con propuesta")
        confirmed[sid] = annotations
    status = {"pilot_users": plan["pilot_users"], "pilot_comments": len(sample), "ai_proposals": len(proposals),
        "human_confirmed": len(confirmed), "pending_human": len(sample) - len(confirmed),
        "pending_users_outside_pilot": plan["pending_users"], "ready": len(confirmed) == len(sample),
        "limitation": plan["limitation"], "test_evaluated": False, "production_analysis": False}
    closure = folder / "reference_manifest.json"
    if closure.exists():
        sealed = json.loads(closure.read_text())
        expected = {"gold_sha256": "pilot_gold.csv", "human_review_sha256": "human_review.csv",
                    "proposals_sha256": "ai_proposals.json"}
        if sealed.get("protocol") != PROTOCOL or any(sha256(folder / name) != sealed.get(key) for key, name in expected.items()):
            raise ValueError("Referencia piloto cerrada alterada; conservar sus versiones originales")
    elif (folder / "pilot_gold.csv").exists():
        raise ValueError("Referencia piloto sin manifiesto de cierre")
    return status, confirmed, sample


def import_reference(settings, run, cohort_id, *, check_only=False):
    status, confirmed, sample = reference_status(settings, run, cohort_id)
    if check_only:
        return status
    if not status["ready"]:
        raise ValueError("Faltan confirmaciones humanas; las propuestas IA no son referencia")
    folder, _, _, _ = checked(settings, run, cohort_id)
    if (folder / "pilot_gold.csv").exists():
        raise FileExistsError("No sobrescribir referencia piloto")
    sample["annotation_json"] = sample.sample_id.map(lambda sid: json.dumps(confirmed[sid], ensure_ascii=False))
    save_csv(sample, folder / "pilot_gold.csv")
    atomic_json(folder / "reference_manifest.json", {**status, "closed_at": stamp(), "protocol": PROTOCOL,
        "gold_sha256": sha256(folder / "pilot_gold.csv"), "human_review_sha256": sha256(folder / "human_review.csv"),
        "proposals_sha256": sha256(folder / "ai_proposals.json"), "training_allowed": False})
    return status


def review(settings, run, cohort_id):
    from .review import edit_items
    folder, _, _, _ = checked(settings, run, cohort_id)
    status, _, _ = reference_status(settings, run, cohort_id)
    if (folder / "pilot_gold.csv").exists():
        raise ValueError("Referencia cerrada")
    proposals = json.loads((folder / "ai_proposals.json").read_text())
    frame = read_csv(folder / "human_review.csv")
    print("Revisión humana del piloto por usuario. Revisa también objetivos omitidos; no hay resultados AP.")
    print(json.dumps(status, ensure_ascii=False))
    reviewer = input("Tu identificador de revisor (:q para salir): ").strip()
    if not reviewer or reviewer == ":q":
        return
    targets = {x["target_id"]: x["name"] for x in load_registry(settings["registry"])["targets"]}
    print("positive=apoyo; negative=rechazo; neutral=sin valoración; mixed=ambas; not_evaluable=incierto.")
    print("[] significa ausencia de objetivo político explícito identificable. Revisa todo el texto y las omisiones.")
    position = 0
    try:
        for index, row in frame.iterrows():
            if row.sample_id not in proposals or row.review_complete.lower() in ("true", "1", "yes", "si", "sí"):
                continue
            proposal = proposals[row.sample_id]
            position += 1
            print(f"\n[{position}/{status['pending_human']} pendientes]\n{row.text}\nPropuesta IA:")
            for item in proposal["annotations"]:
                mention = row.text[item["mention_start"]:item["mention_end"]]
                print(f"  {item['target_id']} | {mention} | {item['valence']}")
            if not proposal["annotations"]:
                print("  Sin objetivo político explícito identificable (lista vacía).")
            print(proposal["note"])
            while True:
                action = input("[a] aceptar, [e] editar, [s] dejar pendiente, [q] salir: ").strip().lower()
                if action in ("a", "e", "s", "q", ":q"):
                    break
            if action in ("q", ":q"):
                break
            if action == "s":
                continue
            annotations = proposal["annotations"] if action == "a" else edit_items(row.text, targets)
            if annotations is None:
                break
            annotations = validate_items(annotations, row.text, set(targets))
            if input("¿Confirmas que revisaste todo el comentario y sus objetivos? [s/N]: ").strip().lower() not in ("s", "si", "sí"):
                continue
            for key, value in {"annotation_json": json.dumps(annotations, ensure_ascii=False), "review_complete": "true",
                "reviewed_at": stamp(), "reviewer_id": reviewer, "decision": "accepted" if annotations == proposal["annotations"] else "modified",
                "proposal_sha256": annotation_digest(proposal["annotations"])}.items():
                frame.at[index, key] = value
            save_csv(frame, folder / "human_review.csv")
    except (EOFError, KeyboardInterrupt):
        print("\nSe conservaron las decisiones ya guardadas.")
