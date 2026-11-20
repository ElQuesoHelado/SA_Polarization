"""Small offline human annotation terminal; does not predict or fill labels."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .common import LABELS, read_csv
from .registry import load_registry


def edit_items(text: str, targets: dict) -> list[dict] | None:
    """Build a human correction; None means leave the current comment pending."""
    items = []
    while True:
        target = input("target_id o unregistered:nombre; Enter para terminar; :q para salir: ").strip()
        if target == ":q":
            return None
        if not target:
            return items
        if target not in targets and (not target.startswith("unregistered:") or not target.split(":", 1)[1].strip()):
            print("Objetivo desconocido. Usa el ID del registro o unregistered:nombre.")
            continue
        if any(item["target_id"] == target for item in items):
            print("El actor ya está anotado. Un actor se etiqueta una vez por comentario.")
            continue
        mention = input("Copia exactamente la mención dentro del comentario: ")
        offsets, start = [], 0
        while mention and (position := text.find(mention, start)) >= 0:
            offsets.append(position)
            start = position + len(mention)
        if not offsets:
            print("La mención no aparece literalmente. Se requiere mención explícita.")
            continue
        occurrence = 0
        if len(offsets) > 1:
            try:
                occurrence = int(input(f"Hay {len(offsets)} coincidencias; elige 1..{len(offsets)}: ")) - 1
            except ValueError:
                continue
            if not 0 <= occurrence < len(offsets):
                continue
        label = input("Valencia [positive/negative/neutral/mixed/not_evaluable]: ").strip()
        if label not in LABELS:
            print("Etiqueta inválida; vuelve a añadir el actor.")
            continue
        position = offsets[occurrence]
        items.append({"target_id": target, "valence": label, "mention_start": position, "mention_end": position + len(mention)})


def assisted_review(settings: dict, run: Path, *, pilot_only: bool = False) -> None:
    from .assisted import checked_sample, load_proposals, save_csv, annotation_digest, PROTOCOL
    from .annotations import validate_items
    from .common import stamp
    sample, manifest = checked_sample(settings, run)
    if manifest["status"] == "human_reviewed_assisted":
        raise ValueError("La revisión está cerrada; conservarla antes de cambiar etiquetas")
    proposals = load_proposals(settings, run, sample).set_index("sample_id")
    from .revision import load_inherited
    inherited = load_inherited(settings, run, sample)
    path = run / "annotations" / "human_review.csv"
    frame = read_csv(path)
    if frame.sample_id.duplicated().any() or set(frame.sample_id) != set(sample.sample_id):
        raise ValueError("El formulario humano tiene IDs duplicados o diferentes de la muestra")
    expected = sample.set_index("sample_id")
    if any(row.text != expected.loc[row.sample_id].text or row.comment_id != expected.loc[row.sample_id].comment_id for row in frame.itertuples()):
        raise ValueError("Texto o identificador editado en formulario humano")
    targets = {item["target_id"]: item["name"] for item in load_registry(settings["registry"])["targets"]}
    print("Propuestas de IA pendientes de tu revisión. No son decisiones humanas confirmadas.")
    if inherited:
        print(f"Revisiones humanas heredadas verificadas: {len(inherited)}. No requieren otra confirmación.")
    print("Objetivos:", json.dumps(targets, ensure_ascii=False))
    print("positive=apoyo; negative=rechazo; neutral=mención sin valoración; mixed=ambas; not_evaluable=incierto.")
    print("Revisa también omisiones. [] significa que no hay objetivo político explícito identificable.")
    if manifest.get("annotation_protocol") != PROTOCOL:
        raise ValueError("Protocolo asistido requerido")
    available = [row.sample_id for row in frame.itertuples() if row.sample_id not in inherited
                 and row.review_complete.lower() not in ("true", "1", "yes", "si", "sí")
                 and (not pilot_only or row.pilot.lower() == "true") and row.sample_id in proposals.index]
    print(f"Comentarios con propuesta pendientes de revisión: {len(available)}.")
    pending_without_proposal = 0
    position = 0
    try:
        for index, row in frame.iterrows():
            if row.sample_id in inherited:
                continue
            if row.review_complete.lower() in ("true", "1", "yes", "si", "sí"):
                continue
            if pilot_only and row.pilot.lower() != "true":
                continue
            if row.sample_id not in proposals.index:
                pending_without_proposal += 1
                continue
            suggestion = proposals.loc[row.sample_id]
            ai = validate_items(json.loads(suggestion.ai_annotation_json), row.text, set(targets))
            position += 1
            print(f"\n[{position}/{len(available)} pendientes] {row.sample_id}\n{row.text}")
            if row.parent_text:
                print(f"Comentario padre (solo contexto): {row.parent_text}")
            print(f"Título (solo contexto): {row.post_title}")
            print("Propuesta IA:")
            if not ai:
                print("  Sin objetivo político explícito identificable (lista vacía).")
            for item in ai:
                print(f"  {item['target_id']} | {row.text[item['mention_start']:item['mention_end']]} | {item['valence']}")
            print("Nota IA:", suggestion.ai_note)
            while True:
                action = input("[a] aceptar, [e] rehacer/corregir objetivos, [s] dejar pendiente, [q] salir: ").strip().lower()
                if action in ("a", "e", "s", "q", ":q"):
                    break
            if action in ("q", ":q"):
                return
            if action == "s":
                continue
            items = ai if action == "a" else edit_items(row.text, targets)
            if items is None:
                return
            items = validate_items(items, row.text, set(targets))
            print("Decisión final:", json.dumps(items, ensure_ascii=False))
            if input("¿Confirmas que revisaste todo el comentario y sus objetivos? [s/N]: ").strip().lower() not in ("s", "si", "sí"):
                continue
            for key, value in {"annotation_json": json.dumps(items, ensure_ascii=False), "review_complete": "true",
                    "reviewed_at": stamp(), "reviewer_id": "user", "decision": "accepted" if items == ai else "modified",
                    "proposal_sha256": annotation_digest(ai)}.items():
                frame.at[index, key] = value
            save_csv(frame, path)
        print(f"Fin de los disponibles. Pendientes sin propuesta: {pending_without_proposal}.")
    except (EOFError, KeyboardInterrupt):
        print("\nLos comentarios confirmados están guardados; el actual permanece pendiente.")


def annotate(settings: dict, run: Path, reviewer: int, *, pilot_only: bool = False) -> None:
    if reviewer not in (1, 2):
        raise ValueError("reviewer debe ser 1 o 2")
    manifest = run / "annotations" / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()).get("annotation_protocol") == "ai_assisted_single_human_v1":
        raise ValueError("Esta ejecución usa revisión asistida; utiliza assisted-review")
    path = run / "annotations" / f"reviewer_{reviewer}.csv"
    frame = read_csv(path)
    registry = load_registry(settings["registry"])
    targets = {item["target_id"]: item["name"] for item in registry["targets"]}
    print("Revisión humana independiente. No hay predicciones ni etiquetas del canal.")
    print("Objetivos del registro:", json.dumps(targets, ensure_ascii=False))
    try:
        for index, row in frame.iterrows():
            if row.review_complete.lower() in ("true", "1", "yes", "si", "sí"):
                continue
            if pilot_only and row.pilot.lower() != "true":
                continue
            print(f"\n[{index + 1}/{len(frame)}] {row.sample_id}\n{row.text}")
            if row.parent_text:
                print(f"Comentario padre (solo contexto): {row.parent_text}")
            print(f"Título (solo contexto): {row.post_title}")
            items = []
            while True:
                target = input("target_id o unregistered:nombre; Enter para terminar; :q para salir: ").strip()
                if target == ":q":
                    return
                if not target:
                    break
                if target not in targets and (not target.startswith("unregistered:") or not target.split(":", 1)[1].strip()):
                    print("Objetivo desconocido. Usa el ID del registro o unregistered:nombre.")
                    continue
                if any(item["target_id"] == target for item in items):
                    print("El actor ya está anotado. Un actor se etiqueta una vez por comentario.")
                    continue
                mention = input("Copia exactamente la mención dentro del comentario: ")
                offsets = []
                start = 0
                while mention and (position := row.text.find(mention, start)) >= 0:
                    offsets.append(position)
                    start = position + len(mention)
                if not offsets:
                    print("La mención no aparece literalmente. El análisis principal requiere mención explícita.")
                    continue
                occurrence = 0
                if len(offsets) > 1:
                    try:
                        occurrence = int(input(f"Hay {len(offsets)} coincidencias; elige 1..{len(offsets)}: ")) - 1
                    except ValueError:
                        continue
                    if not 0 <= occurrence < len(offsets):
                        continue
                label = input("Valencia [positive/negative/neutral/mixed/not_evaluable]: ").strip()
                if label not in LABELS:
                    print("Etiqueta inválida; vuelve a añadir el actor.")
                    continue
                position = offsets[occurrence]
                items.append({"target_id": target, "valence": label, "mention_start": position, "mention_end": position + len(mention)})
            print("Anotación:", json.dumps(items, ensure_ascii=False))
            if input("¿Guardar como revisado? [s/N]: ").strip().lower() not in ("s", "si", "sí"):
                print("Sin guardar este registro; permanece pendiente.")
                continue
            frame.at[index, "annotation_json"] = json.dumps(items, ensure_ascii=False)
            frame.at[index, "review_complete"] = "true"
            fd, name = tempfile.mkstemp(dir=path.parent, prefix=".human-review-")
            os.close(fd)
            try:
                frame.to_csv(name, index=False)
                os.replace(name, path)
            finally:
                Path(name).unlink(missing_ok=True)
    except (EOFError, KeyboardInterrupt):
        print("\nRevisión interrumpida; los registros confirmados están guardados.")
