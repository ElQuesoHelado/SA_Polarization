"""AI proposals and human decisions have distinct storage and closure conditions."""
from __future__ import annotations

import json
import re

import pandas as pd

from ..annotations import validate_items
from ..assisted import annotation_digest, save_csv
from ..common import atomic_json, read_csv, sha256, stamp
from ..registry import Matcher, load_registry
from .state import seal, verify, verify_seal, lock


def folder_for(study, name):
    if not re.fullmatch(r"benchmark|cohort_[0-9]{4}", name):
        raise ValueError("Muestra inválida")
    return study / "annotations" / name


def initialize(study, name, sample):
    folder = folder_for(study, name)
    folder.mkdir(parents=True, exist_ok=False)
    sample = sample.sample(frac=1, random_state=57).reset_index(drop=True)
    sample.to_csv(folder / "sample.csv", index=False)
    hints = sample.candidates_json.map(lambda value: json.dumps([
        {k: m[k] for k in ("target_id", "target_name", "mention_start", "mention_end")} for m in json.loads(value)], ensure_ascii=False))
    sample[["sample_id", "text"]].assign(target_hints_json=hints).to_csv(folder / "reading_queue.csv", index=False)
    form = sample[["sample_id", "text"]].copy()
    for key in ("review_complete", "annotation_json", "reviewer_id", "reviewed_at", "decision", "proposal_sha256"):
        form[key] = ""
    save_csv(form, folder / "human_review.csv")
    atomic_json(folder / "ai_proposals.json", {})
    seal(folder, ["sample.csv", "reading_queue.csv"], name=name,
         study_freeze_sha256=sha256(study / "freeze.json"), evidence_policy="explicit_only",
         human_mode="blind" if name == "benchmark" else "assisted")
    atomic_json(folder / "proposal_state.json", dict(sha256=sha256(folder / "ai_proposals.json"), batches=[]))
    return folder


def checked(study, name):
    verify(study, frozen=True)
    folder = folder_for(study, name)
    manifest = verify_seal(folder)
    if manifest["study_freeze_sha256"] != sha256(study / "freeze.json"):
        raise ValueError("La muestra pertenece a otro snapshot")
    state = json.loads((folder / "proposal_state.json").read_text())
    if state["sha256"] != sha256(folder / "ai_proposals.json"):
        raise ValueError("Propuestas alteradas fuera del importador")
    return folder, read_csv(folder / "sample.csv"), manifest, state


def import_proposals(study, name, batch, registry):
    folder, sample, _, state = checked(study, name)
    if (folder / "reference.json").exists():
        raise ValueError("Referencia cerrada")
    if (batch.get("sample_sha256") != sha256(folder / "sample.csv") or not batch.get("origin", "").strip()
            or not isinstance(batch.get("proposals"), list) or not batch["proposals"]):
        raise ValueError("Lote sin hash, procedencia o propuestas")
    targets = {t["target_id"] for t in load_registry(registry, frozen=True)["targets"]}
    indexed = sample.set_index("sample_id")
    stored = json.loads((folder / "ai_proposals.json").read_text())
    for item in batch["proposals"]:
        sid = item.get("sample_id")
        if not isinstance(item.get("annotations"), list):
            raise ValueError("Propuesta pendiente: annotations debe ser una lista explícita")
        if sid not in indexed.index or sid in stored or not item.get("note", "").strip():
            raise ValueError("ID ajeno, duplicado o propuesta sin nota")
        if any(a.get("evidence_scope", "explicit") != "explicit" for a in item["annotations"]):
            raise ValueError("Las referencias contextuales no entran al principal explicit_only")
        items = validate_items(item["annotations"], indexed.loc[sid, "text"], targets)
        stored[sid] = dict(annotations=items, note=item["note"], origin=batch["origin"], created_at=stamp())
    destination = folder / "batches"
    destination.mkdir(exist_ok=True)
    path = destination / f"{len(state['batches'])+1:05d}.json"
    atomic_json(path, batch)
    atomic_json(folder / "ai_proposals.json", stored)
    state.update(sha256=sha256(folder / "ai_proposals.json"), batches=[*state["batches"], dict(path=path.name, sha256=sha256(path))])
    atomic_json(folder / "proposal_state.json", state)
    return dict(proposals=len(stored), comments=len(sample), human_decisions_written=0)


def decisions(study, name, registry, stage):
    folder, sample, manifest, _ = checked(study, name)
    targets = {t["target_id"] for t in load_registry(registry, frozen=True)["targets"]}
    proposals = json.loads((folder / "ai_proposals.json").read_text())
    if stage == "provisional":
        if set(proposals) != set(sample.sample_id):
            raise ValueError("Faltan propuestas; no analizar una muestra parcialmente anotada")
        indexed = sample.set_index("sample_id")
        result = {sid: validate_items(value["annotations"], indexed.loc[sid, "text"], targets)
                  for sid, value in proposals.items()}
        return sample.assign(annotation_json=sample.sample_id.map(lambda sid: json.dumps(result[sid], ensure_ascii=False)))
    if stage != "final":
        raise ValueError("stage debe ser provisional o final")
    if (folder / "reference.json").exists():
        verify_seal(folder, "reference.json")
    human = read_csv(folder / "human_review.csv")
    if human.sample_id.duplicated().any() or set(human.sample_id) != set(sample.sample_id):
        raise ValueError("Formulario humano con identidades alteradas")
    expected = sample.set_index("sample_id")
    parsed = {}
    for row in human.to_dict("records"):
        sid = row["sample_id"]
        if row["text"] != expected.loc[sid, "text"]:
            raise ValueError("Texto del formulario alterado")
        if row["review_complete"].lower() != "true" or not row["reviewer_id"].strip() or not row["reviewed_at"].strip():
            raise ValueError("Revisión humana incompleta")
        items = validate_items(json.loads(row["annotation_json"]), row["text"], targets)
        if manifest["human_mode"] == "assisted":
            if sid not in proposals or row["proposal_sha256"] != annotation_digest(proposals[sid]["annotations"]):
                raise ValueError("Decisión asistida sin propuesta íntegra")
            expected_decision = "accepted" if items == proposals[sid]["annotations"] else "modified"
            if row["decision"] != expected_decision:
                raise ValueError("Procedencia de decisión humana incorrecta")
        elif row["decision"] != "blind" or row["proposal_sha256"]:
            raise ValueError("La referencia independiente requiere decisión ciega")
        parsed[sid] = items
    return sample.assign(annotation_json=sample.sample_id.map(lambda sid: json.dumps(parsed[sid], ensure_ascii=False)))


def close_reference(study, name, registry):
    folder, _, _, _ = checked(study, name)
    frame = decisions(study, name, registry, "final")
    if (folder / "reference.json").exists():
        verify_seal(folder, "reference.json")
        return folder
    frame.to_csv(folder / "gold.csv", index=False)
    seal(folder, ["gold.csv", "human_review.csv", "ai_proposals.json"], filename="reference.json",
         status="human_reviewed", single_reviewer=True, interrater_agreement=None)
    return folder


def review(study, name, registry, *, batch_number=None):
    folder = folder_for(study, name)
    if not folder.is_dir():
        raise FileNotFoundError("La muestra todavía no está preparada")
    with lock(folder / "human_review.lock"):
        return _review(study, name, registry, batch_number=batch_number)


def _review(study, name, registry, *, batch_number=None):
    from ..review import edit_items
    folder, sample, manifest, _ = checked(study, name)
    if (folder / "reference.json").exists():
        raise ValueError("Referencia cerrada")
    form = read_csv(folder / "human_review.csv")
    from .batches import indices, SIZE
    pending = form.index[~form.review_complete.str.lower().eq("true")].tolist()
    if not pending:
        print("Muestra completamente revisada.")
        return
    number = batch_number if batch_number is not None else pending[0] // SIZE + 1
    selected = list(indices(len(form), number))
    print(f"Tanda {number}/{(len(form)+SIZE-1)//SIZE}; pendientes en la muestra: {len(pending)}")
    proposals = json.loads((folder / "ai_proposals.json").read_text())
    targets = {t["target_id"]: t["name"] for t in load_registry(registry)["targets"]}
    reviewer = input("Tu identificador humano (:q para salir): ").strip()
    if not reviewer or reviewer == ":q":
        return
    blind = manifest["human_mode"] == "blind"
    print("Registro de identidades (sin bloques):", json.dumps(targets, ensure_ascii=False))
    print("positive=valoración favorable; negative=desfavorable; neutral=mención sin valoración; mixed=ambas; not_evaluable=incierto.")
    print("Revisar objetivos omitidos. unregistered:nombre conserva objetivos no registrados. Solo evidencia explícita del texto.")
    for index, row in form.iloc[selected].iterrows():
        if row.review_complete.lower() == "true":
            continue
        print("\n" + row.text)
        if blind:
            print("Anotación ciega: identifica todos los objetivos explícitos; [] también requiere lectura completa.")
            items = edit_items(row.text, targets)
            decision, digest = "blind", ""
        else:
            if row.sample_id not in proposals:
                print("Propuesta aún pendiente; se conserva sin revisar.")
                continue
            proposal = proposals[row.sample_id]
            print(json.dumps(proposal, ensure_ascii=False, indent=2))
            action = input("[a] aceptar, [e] editar, [s] pendiente, [q] salir: ").strip().lower()
            if action == "q":
                break
            if action not in ("a", "e"):
                continue
            items = proposal["annotations"] if action == "a" else edit_items(row.text, targets)
            digest = annotation_digest(proposal["annotations"])
            decision = "accepted" if items == proposal["annotations"] else "modified"
        if items is None:
            break
        if input("¿Leíste todo el texto y comprobaste omisiones? [s/N]: ").strip().lower() != "s":
            continue
        form.loc[index, ["review_complete", "annotation_json", "reviewer_id", "reviewed_at", "decision", "proposal_sha256"]] = [
            "true", json.dumps(items, ensure_ascii=False), reviewer, stamp(), decision, digest]
        save_csv(form, folder / "human_review.csv")


def cohort_samples(study, registry, stage):
    folders = sorted((study / "annotations").glob("cohort_[0-9][0-9][0-9][0-9]"))
    frames = [decisions(study, f.name, registry, stage) for f in folders]
    if not frames:
        raise ValueError("No hay lotes por usuario")
    frame = pd.concat(frames, ignore_index=True)
    if frame.comment_id.duplicated().any():
        raise ValueError("Comentarios repetidos entre lotes")
    return frame


def next_batch(settings, plan, study, registry, *, stage="provisional"):
    from .analysis import events_from_annotations, scores
    verify(study, frozen=True)
    folders = sorted((study / "annotations").glob("cohort_[0-9][0-9][0-9][0-9]"))
    ranked = read_csv(study / "eligible_users.csv")
    used = set()
    if folders:
        frame = cohort_samples(study, registry, stage)
        used = set(frame.user_id)
        expected = set(ranked.iloc[:len(used)].user_id)
        if used != expected:
            raise ValueError("Los lotes no conservan el prefijo del orden congelado")
        current = scores(events_from_annotations(frame, registry), settings)
        if int(current.paired.sum()) >= plan["comparable_users"]:
            return dict(status="target_reached", stage=stage, screened_users=len(used), comparable=int(current.paired.sum()))
    selected = ranked.iloc[len(used):len(used)+plan["batch_users"]]
    if selected.empty:
        return dict(status="frame_exhausted", screened_users=len(used))
    corpus = read_csv(study / "corpus.csv")
    sample = corpus.loc[corpus.user_id.isin(set(selected.user_id))].copy()
    return initialize(study, f"cohort_{len(folders)+1:04d}", sample)


def init_benchmark(study):
    verify(study, frozen=True)
    return initialize(study, "benchmark", read_csv(study / "benchmark.csv"))
