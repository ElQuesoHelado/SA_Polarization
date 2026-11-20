"""Prepare a label-free user validation cohort; never scores AP or opens final gold."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from .annotations import text_key
from .common import POLITICAL, atomic_json, sha256, stamp
from .diagnostics import EVENT_COLUMNS, opportunities, protected_files
from .metrics import partition_videos
from .registry import Matcher, load_registry, registry_fingerprint

PROTOCOL = "targeted-user-cohort-design-v1"
IDENTITY = ("user_id", "post_id", "comment_id")
COMMENT_COLUMNS = ("sample_id", "user_id", "comment_id", "post_id", "channel_id", "comment_published_at",
                   "comment_type", "parent_id", "corpus", "text", "fold", "candidates_json", "user_inclusion_probability")


def load_exclusions(settings: dict, run: Path) -> tuple[dict, dict]:
    """Read only sampling metadata; no human annotation payload is decoded."""
    paths = [run / "annotations/sampling_manifest.csv"]
    original = settings["workspace"] / "targeted_20261114/annotations/sampling_manifest.csv"
    if original.exists() and original not in paths:
        paths.append(original)
    paths.extend(sorted((run / "experiments").glob("*/sample.csv")))
    excluded = {key: set() for key in (*IDENTITY, "text_key")}
    hashes = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                for key in IDENTITY:
                    if row[key]:
                        excluded[key].add(row[key])
                excluded["text_key"].add(text_key(row["text"]))
        hashes[str(path.resolve())] = sha256(path)
    return excluded, hashes


def exclusion_reason(row: dict, excluded: dict) -> str:
    for key in IDENTITY:
        if row[key] in excluded[key]:
            return key
    return "text_key" if text_key(row["text"]) in excluded["text_key"] else ""


def eligible_frame(records, matcher: Matcher, settings: dict, excluded: dict) -> tuple[pd.DataFrame, dict]:
    users, all_users, exclusions, seen = Counter(), Counter(), Counter(), set()
    events, all_events = [], []
    eligible_rows = 0
    for row in records:
        if not row["comment_id"] or row["comment_id"] in seen or row["corpus"] != "main" or not row["post_id"]:
            raise ValueError("Corpus principal con identidad vacía, duplicada o ajena")
        seen.add(row["comment_id"])
        if not row["user_id"]:
            exclusions["missing_user"] += 1
            continue
        all_users[row["user_id"]] += 1
        groups = {m["target_group"] for m in matcher.find(row["text"], row["comment_published_at"])} & set(POLITICAL)
        found = [{**{key: row.get(key, "") for key in EVENT_COLUMNS}, "target_group": group} for group in sorted(groups)]
        all_events.extend(found)
        reason = exclusion_reason(row, excluded)
        if reason:
            exclusions[reason] += 1
            continue
        users[row["user_id"]] += 1
        eligible_rows += 1
        events.extend(found)
    full = opportunities(pd.DataFrame(all_events, columns=EVENT_COLUMNS), all_users, settings, seed=settings["seed"])
    allowed = opportunities(pd.DataFrame(events, columns=EVENT_COLUMNS), users, settings, seed=settings["seed"])
    frame = allowed.loc[allowed.potentially_paired].copy()
    frame["noncandidate_comments"] = frame.total_comments - frame.political_mention_comments
    return frame, {"main_comments": len(seen), "identified_users": len(all_users),
        "unrestricted_potential_users": int(full.potentially_paired.sum()), "eligible_comments": eligible_rows,
        "eligible_users": len(users), "potential_users_after_exclusions": len(frame),
        "excluded_comments_first_reason": dict(exclusions)}


def rank_users(frame: pd.DataFrame, seed: int) -> pd.DataFrame:
    if frame.user_id.duplicated().any():
        raise ValueError("Usuarios duplicados en marco de selección")
    frame = frame.copy()
    frame["selection_rank_hash"] = frame.user_id.map(lambda user: hashlib.sha256(f"user-cohort:{seed}:{user}".encode()).hexdigest())
    return frame.sort_values(["selection_rank_hash", "user_id"]).reset_index(drop=True)


def cost_scenarios(ranked: pd.DataFrame, requested: int) -> pd.DataFrame:
    rows = []
    for size in sorted({25, 50, 100, 200, requested}):
        if size > len(ranked):
            rows.append({"users": size, "available": False, "comments": None, "explicit_political_comments": None,
                         "other_comments_to_review": None})
            continue
        part = ranked.iloc[:size]
        rows.append({"users": size, "available": True, "comments": int(part.total_comments.sum()),
                     "explicit_political_comments": int(part.political_mention_comments.sum()),
                     "other_comments_to_review": int(part.noncandidate_comments.sum())})
    return pd.DataFrame(rows)


def selected_comments(records, selected: pd.DataFrame, matcher: Matcher, excluded: dict, *, seed: int,
                      cohort_id: str, population: int) -> pd.DataFrame:
    users = set(selected.user_id)
    rows = []
    probability = len(users) / population
    for row in records:
        if row["user_id"] not in users or exclusion_reason(row, excluded):
            continue
        matches = matcher.find(row["text"], row["comment_published_at"])
        rows.append({key: row.get(key, "") for key in COMMENT_COLUMNS if key not in
                     ("sample_id", "fold", "candidates_json", "user_inclusion_probability")} | {
            "sample_id": hashlib.sha256(f"{cohort_id}:{row['comment_id']}".encode()).hexdigest()[:20],
            "candidates_json": json.dumps(matches, ensure_ascii=False), "user_inclusion_probability": probability})
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("No hay comentarios para la cohorte seleccionada")
    result["fold"] = partition_videos(result, seed)
    result = result.reindex(columns=COMMENT_COLUMNS).sort_values(["user_id", "fold", "post_id", "comment_id"]).reset_index(drop=True)
    counts = result.groupby("user_id").size()
    if counts.to_dict() != selected.set_index("user_id").total_comments.astype(int).to_dict():
        raise ValueError("La exportación no conserva todos los comentarios elegibles del usuario")
    if result.comment_id.duplicated().any() or result.groupby("post_id").fold.nunique().gt(1).any():
        raise ValueError("Duplicados o video compartido entre A y B")
    return result


def reading_queue(comments: pd.DataFrame) -> pd.DataFrame:
    def hints(value):
        return json.dumps([{key: item[key] for key in ("target_id", "target_name", "mention_start", "mention_end")}
                           for item in json.loads(value)], ensure_ascii=False)
    return comments[["sample_id", "text"]].assign(target_hints_json=comments.candidates_json.map(hints))


def design_user_validation(settings: dict, run: Path, cohort_id: str, *, users: int = 100, seed: int = 57) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", cohort_id) or users < 1:
        raise ValueError("cohort-id inválido o número de usuarios no positivo")
    data = run / "cohorts" / cohort_id
    output = settings["outputs"] / run.name / "cohorts" / cohort_id
    if data.exists() or output.exists():
        raise FileExistsError("La cohorte ya existe; no regenerar ni sobrescribir")
    if (run / "model/test_opened.json").exists():
        raise ValueError("Se requiere prueba final reservada")
    source = json.loads((run / "annotations/manifest.json").read_text())
    if (source.get("status") != "human_reviewed_assisted"
        or sha256(run / "annotations/gold.csv") != source["gold_sha256"]
        or sha256(run / "corpus_main.csv") != source["corpus_main_sha256"]
        or registry_fingerprint(settings["registry"]) != source["registry_sha256"]):
        raise ValueError("Referencia, corpus o registro cambiaron")
    matcher = Matcher(load_registry(settings["registry"], frozen=True))
    excluded, exclusion_inputs = load_exclusions(settings, run)
    print("Verificando archivos protegidos antes de preparar la cohorte", flush=True)
    before = protected_files(settings, run)
    data.mkdir(parents=True); output.mkdir(parents=True)
    atomic_json(output / "manifest.json", {"status": "running", "created_at": stamp()})
    try:
        atomic_json(data / "protected_inputs.json", before)
        with (run / "corpus_main.csv").open(newline="", encoding="utf-8") as handle:
            frame, summary = eligible_frame(csv.DictReader(handle), matcher, settings, excluded)
        ranked = rank_users(frame, seed)
        if len(ranked) < users:
            raise ValueError(f"Solo hay {len(ranked)} usuarios elegibles; no sustituir tamaño ni exclusiones")
        selected = ranked.iloc[:users].copy()
        selected["user_inclusion_probability"] = users / len(ranked)
        selected["user_sampling_weight"] = len(ranked) / users
        ranked.to_csv(data / "eligible_users.csv", index=False)
        selected.to_csv(data / "selected_users.csv", index=False)
        scenarios = cost_scenarios(ranked, users)
        scenarios.to_csv(output / "cost_scenarios.csv", index=False)
        with (run / "corpus_main.csv").open(newline="", encoding="utf-8") as handle:
            comments = selected_comments(csv.DictReader(handle), selected, matcher, excluded, seed=settings["seed"],
                                         cohort_id=cohort_id, population=len(ranked))
        comments.to_csv(data / "comments.csv", index=False)
        reading_queue(comments).to_csv(data / "reading_queue.csv", index=False)
        coverage = comments.groupby("fold").agg(comments=("comment_id", "size"), videos=("post_id", "nunique"), users=("user_id", "nunique"))
        coverage.to_csv(output / "fold_workload.csv")
        summary.update(protocol=PROTOCOL, cohort_id=cohort_id, selected_users=users, selected_comments=len(comments),
            median_comments_per_eligible_user=float(ranked.total_comments.median()),
            median_explicit_comments_per_eligible_user=float(ranked.political_mention_comments.median()),
            selected_without_known_political_candidate=int(comments.candidates_json.map(
                lambda value: not any(x["target_group"] in POLITICAL for x in json.loads(value))).sum()),
            user_inclusion_probability=users / len(ranked), selection_seed=seed, affinity_partition_seed=settings["seed"],
            affinity_positive_share=settings["affinity_positive_share"], minimum_positive_videos=settings["minimum_positive_videos"],
            evaluation_min_interactions=settings["evaluation_min_interactions"], evaluation_min_videos=settings["evaluation_min_videos"],
            exclusion_input_hashes=exclusion_inputs, corpus_main_sha256=source["corpus_main_sha256"],
            registry_sha256=sha256(settings["registry"]), human_gold_sha256=source["gold_sha256"],
            stage="design_only_unannotated", test_labels_decoded=False, final_test_evaluated=False,
            new_labels_generated=False, training_executed=False, production_analysis=False,
            sampling_scope="Muestreo uniforme de usuarios estructuralmente elegibles en el corpus principal tras excluir usuarios/videos/textos ya muestreados. Censo de sus comentarios en videos elegibles; no historial completo de YouTube.",
            limitations="Elegibilidad por candidatos explícitos, no afinidad ni AP confirmadas. 100 usuarios es tamaño operativo por defecto, no cálculo de potencia. Las etiquetas IA previas no son referencia humana.")
        for path, digest in exclusion_inputs.items():
            if sha256(Path(path)) != digest:
                raise ValueError("Cambió una muestra usada para exclusiones")
        if before != protected_files(settings, run) or (run / "model/test_opened.json").exists():
            raise ValueError("Cambió un archivo protegido durante la preparación")
        atomic_json(output / "summary.json", summary)
        write_report(output, data, summary, scenarios)
        artifacts = {str(p.resolve()): sha256(p) for folder in (data, output) for p in sorted(folder.iterdir()) if p.name != "manifest.json"}
        atomic_json(output / "manifest.json", {"status": "complete", "created_at": stamp(), "protocol": PROTOCOL,
            "protected_files_unchanged": len(before), "test_labels_decoded": False, "final_test_evaluated": False,
            "production_analysis": False, "artifacts": artifacts})
    except Exception as error:
        atomic_json(output / "manifest.json", {"status": "failed", "created_at": stamp(), "error": str(error), "production_analysis": False})
        raise
    return output


def write_report(output, data, summary, scenarios):
    lines = ["# Diseño de comprobación por usuario", "", "Preparación sin anotaciones, entrenamiento ni resultados AP.", "",
        f"Usuarios potenciales antes de exclusiones: {summary['unrestricted_potential_users']:,}; después: **{summary['potential_users_after_exclusions']:,}**.",
        f"Cohorte preparada: **{summary['selected_users']} usuarios y {summary['selected_comments']:,} comentarios**.",
        f"Comentarios sin candidato explícito de bloque conocido conservados para revisión: **{summary['selected_without_known_political_candidate']:,}**.", "",
        "## Coste de lectura (muestras anidadas, sin tope por usuario)", "",
        "| Usuarios | Comentarios a leer | Con candidato político explícito | Otros comentarios |", "|---:|---:|---:|---:|"]
    for row in scenarios.to_dict("records"):
        if row["available"]:
            lines.append(f"| {row['users']} | {int(row['comments']):,} | {int(row['explicit_political_comments']):,} | {int(row['other_comments_to_review']):,} |")
        else:
            lines.append(f"| {row['users']} | No disponible | — | — |")
    lines += ["", "## Uso previsto", "",
        "La selección usa solo actividad y candidatos explícitos, sin sentimientos, predicciones o resultado AP. Ninguna fuente editorial se usa como afinidad individual.",
        "A/B conserva videos separados y semilla del método. A permitiría asignar afinidad por positivos; B, contrastar valoraciones propias/externas. Solo las anotaciones futuras podrán confirmar esa posibilidad.",
        "Se excluyen usuarios, videos, comentarios y textos normalizados de las muestras humanas anteriores y de las muestras auxiliares IA, incluida toda metadata de prueba. No se decodifican sus etiquetas.",
        "Se incluyen todos los comentarios elegibles de los usuarios seleccionados, incluso sin coincidencias del registro; no se omiten textos largos ni se truncan. La ausencia de candidato no es neutralidad.",
        "La referencia futura debe distinguir confirmación humana de propuestas IA. Esta preparación no crea decisiones humanas, no estima acuerdo y no convierte etiquetas auxiliares en gold.",
        "Tras contar con una referencia válida, la comprobación deberá comparar asignación de afinidad, pérdida de usuarios comparables y error/signo de AP y gap, además de precisión por bloque y valencia. No usar esta cohorte simultáneamente para entrenar y demostrar exactitud.",
        "No se fijan nuevos umbrales de aprobación ni se promete potencia. El tamaño de 100 usuarios es un presupuesto operativo inicial; los escenarios muestran el coste antes de comprometer otra revisión.", "",
        "## Alcance y siguiente decisión", "", summary["sampling_scope"], summary["limitations"],
        "El alcance excluye el panel y los videos/usuarios previamente muestreados. No representa a todos los usuarios del corpus ni a la población peruana. Se mantiene la prueba final de 500 comentarios reservada.",
        "Siguiente paso: fijar el protocolo de referencia de esta cohorte y su presupuesto de revisión; después comprobar la medida por usuario. No iniciar otra ronda GPU ni análisis productivo desde este diseño.",
        "", f"Archivos locales de preparación: `{data}`. `reading_queue.csv` contiene texto e indicios de objetivo, sin fuentes, partición ni predicciones; no es un formulario humano completado.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
