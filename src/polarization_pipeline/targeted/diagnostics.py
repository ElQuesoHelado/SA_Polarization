"""Local data sufficiency audit. No training, final-test scoring or production AP."""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .common import LABELS, POLITICAL, atomic_json, read_csv, sha256, stamp
from .metrics import partition_videos
from .registry import Matcher, load_registry, registry_fingerprint

EVENT_COLUMNS = ["user_id", "comment_id", "post_id", "channel_id", "party", "month", "target_group"]
STATUSES = ("missed_target", "incomplete_context", "low_confidence", "accepted")


def target_group(target_id: str, targets: dict) -> str:
    if target_id in targets:
        return targets[target_id]["target_group"]
    if target_id.startswith("unregistered:") and target_id.split(":", 1)[1].strip():
        return "unknown"
    raise ValueError(f"Objetivo humano incompatible con el registro: {target_id}")


def weight_summary(weights) -> dict:
    values = np.asarray(list(weights), dtype=float)
    if not len(values):
        return {"units": 0, "weight_sum": 0.0, "effective_n_weights_only": 0.0, "top10_weight_share": 0.0}
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Pesos inválidos")
    return {"units": len(values), "weight_sum": float(values.sum()),
            "effective_n_weights_only": float(values.sum() ** 2 / (values ** 2).sum()),
            "top10_weight_share": float(np.sort(values)[-10:].sum() / values.sum())}


def load_development(run: Path) -> tuple[pd.DataFrame, dict]:
    """Skip reserved rows BEFORE decoding annotation_json; inspect only split metadata."""
    rows, videos, ids = [], defaultdict(set), defaultdict(set)
    with (run / "annotations/gold.csv").open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            split = record["split"]
            if split not in ("train", "validation", "test"):
                raise ValueError("Partición de referencia desconocida")
            videos[split].add(record["post_id"])
            if record["sample_id"] in set().union(*ids.values()):
                raise ValueError("sample_id duplicado")
            ids[split].add(record["sample_id"])
            if split == "test":
                continue
            probability = float(record["sampling_probability"])
            if not math.isfinite(probability) or not 0 < probability <= 1:
                raise ValueError("Probabilidad muestral inválida")
            record["items"] = json.loads(record["annotation_json"])
            record["weight"] = 1 / probability
            if len({item["target_id"] for item in record["items"]}) != len(record["items"]):
                raise ValueError("Objetivos humanos duplicados")
            if any(item["valence"] not in LABELS for item in record["items"]):
                raise ValueError("Etiqueta humana desconocida")
            rows.append(record)
    for first, second in (("train", "validation"), ("train", "test"), ("validation", "test")):
        if videos[first] & videos[second]:
            raise ValueError("Videos compartidos entre particiones")
    if not rows or not ids["validation"]:
        raise ValueError("Se requiere desarrollo y validación")
    return pd.DataFrame(rows), {"comments_by_split": {key: len(value) for key, value in ids.items()},
                                "test_labels_decoded": False}


def composition(path: Path, matcher: Matcher, corpus: str) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    counters = {key: Counter() for key in ("party", "channel_id", "month", "comment_type", "target_count")}
    users, videos, seen = Counter(), set(), set()
    actors, events = Counter(), []
    political_comments = matched_comments = missing_users = 0
    with path.open(newline="", encoding="utf-8") as handle:
        for index, record in enumerate(csv.DictReader(handle), 1):
            identifier = record["comment_id"]
            if not identifier or identifier in seen:
                raise ValueError(f"comment_id vacío o duplicado en {corpus}")
            allowed_corpora = ("panel", "audit_panel") if corpus == "panel" else ("main",)
            if record["corpus"] not in allowed_corpora or not record["post_id"] or not record["channel_id"]:
                raise ValueError(f"Identidad de corpus/video/canal inválida en {corpus}")
            seen.add(identifier)
            videos.add(record["post_id"])
            user = record["user_id"]
            if user:
                users[user] += 1
            else:
                missing_users += 1
            date = record["comment_published_at"]
            month = date[:7] if re.match(r"\d{4}-\d{2}", date) else "missing"
            for key in ("party", "channel_id", "comment_type"):
                counters[key][record.get(key, "") or "missing"] += 1
            counters["month"][month] += 1
            found = matcher.find(record["text"], date)
            counters["target_count"][str(len(found))] += 1
            matched_comments += bool(found)
            groups = {item["target_group"] for item in found if item["target_group"] in POLITICAL}
            political_comments += bool(groups)
            for item in found:
                actors[(item["target_id"], item["target_group"])] += 1
            for group in sorted(groups):
                if user:
                    events.append((user, identifier, record["post_id"], record["channel_id"],
                                   record["party"], month, group))
            if index % 100000 == 0:
                print(f"Auditoría {corpus}: {index:,} comentarios", flush=True)
    rows = len(seen)
    ordered_users = sorted(users.values(), reverse=True)
    top_users = max(1, math.ceil(len(users) * .01))
    summary = {"rows": rows, "videos": len(videos), "channels": len(counters["channel_id"]),
               "identified_users": len(users), "rows_without_user": missing_users,
               "single_comment_users": sum(value == 1 for value in users.values()),
               "top5_channels_share": sum(sorted(counters["channel_id"].values(), reverse=True)[:5]) / rows if rows else 0,
               "top1percent_users_comment_share": sum(ordered_users[:top_users]) / sum(ordered_users) if ordered_users else 0,
               "top1percent_users_count_rounded_up": min(top_users, len(users)),
               "explicit_candidate_comments": matched_comments, "known_political_candidate_comments": political_comments,
               "candidate_pairs": sum(actors.values()), "political_block_events_identified_users": len(events),
               "source_counts": dict(counters["party"])}
    distributions = [{"dimension": key, "value": value, "comments": count,
                      "share_all_comments": count / rows} for key, counter in counters.items()
                     for value, count in sorted(counter.items())]
    actor_rows = [{"target_id": target, "target_group": group, "candidate_comments": count}
                  for (target, group), count in sorted(actors.items())]
    summary["actors"] = actor_rows
    summary["user_comment_counts"] = users
    return summary, pd.DataFrame(events, columns=EVENT_COLUMNS), pd.DataFrame(distributions), pd.DataFrame(actor_rows)


def opportunities(events: pd.DataFrame, users: Counter, settings: dict, *, seed: int, reverse: bool = False) -> pd.DataFrame:
    """Optimistic structural ceiling: each mention COULD be evaluable, never a sentiment assignment."""
    frame = events.drop_duplicates(["comment_id", "target_group"]).copy()
    frame["fold"] = partition_videos(frame, seed)
    result = pd.DataFrame({"user_id": sorted(users)})
    result["total_comments"] = result.user_id.map(users)
    result = result.set_index("user_id")
    assignment, evaluation = ("B", "A") if reverse else ("A", "B")
    a, b = frame.loc[frame.fold.eq(assignment)], frame.loc[frame.fold.eq(evaluation)]
    for group in POLITICAL:
        result[f"assignment_videos_{group}"] = a.loc[a.target_group.eq(group)].groupby("user_id").post_id.nunique()
        result[f"assignment_events_{group}"] = a.loc[a.target_group.eq(group)].groupby("user_id").size()
        result[f"evaluation_events_{group}"] = b.loc[b.target_group.eq(group)].groupby("user_id").size()
    result["political_mention_comments"] = frame.groupby("user_id").comment_id.nunique()
    result["evaluation_videos"] = b.groupby("user_id").post_id.nunique()
    result = result.fillna(0)
    result["assignment_possible"] = False
    for group in POLITICAL:
        result["assignment_possible"] |= (result[f"assignment_videos_{group}"].ge(settings["minimum_positive_videos"])
                                           & result[f"assignment_events_{group}"].ge(2))
    result["both_blocks_evaluation"] = (result.evaluation_events_izquierda.gt(0) & result.evaluation_events_derecha.gt(0))
    result["evaluation_possible"] = (result.both_blocks_evaluation
        & result[[f"evaluation_events_{group}" for group in POLITICAL]].sum(axis=1).ge(settings["evaluation_min_interactions"])
        & result.evaluation_videos.ge(settings["evaluation_min_videos"]))
    result["potentially_paired"] = result.assignment_possible & result.evaluation_possible
    return result.reset_index()


def annotation_support(gold: pd.DataFrame, targets: dict) -> tuple[pd.DataFrame, dict]:
    rows = []
    for record in gold.to_dict("records"):
        for item in record["items"]:
            rows.append({"split": record["split"], "target_id": item["target_id"],
                         "target_group": target_group(item["target_id"], targets), "valence": item["valence"],
                         "comment_type": record["comment_type"], "party": record["party"],
                         "weight": record["weight"]})
    units = pd.DataFrame(rows)
    support = []
    if not units.empty:
        for (split, valence), group in units.groupby(["split", "valence"]):
            support.append({"dimension": "all", "split": split, "value": "all", "valence": valence,
                            **weight_summary(group.weight), "low_support_under_10": len(group) < 10})
        for dimension in ("valence", "target_id", "target_group", "comment_type", "party"):
            for (split, value, valence), group in units.groupby(["split", dimension, "valence"] if dimension != "valence" else ["split", "target_group", "valence"]):
                support.append({"dimension": dimension if dimension != "valence" else "target_group_valence",
                                "split": split, "value": value, "valence": valence,
                                **weight_summary(group.weight), "low_support_under_10": len(group) < 10})
    observed = {(row["split"], row["value"], row["valence"]) for row in support if row["dimension"] == "target_group_valence"}
    for split in sorted(gold.split.unique()):
        for group in POLITICAL:
            for valence in LABELS[:3]:
                if (split, group, valence) not in observed:
                    support.append({"dimension": "target_group_valence", "split": split, "value": group, "valence": valence,
                                    **weight_summary([]), "low_support_under_10": True})
    summary = {}
    for split, group in gold.groupby("split"):
        users = group.loc[group.user_id.ne("")].user_id.value_counts()
        summary[split] = {"comments": len(group), "users": len(users), "single_comment_users": int(users.eq(1).sum()),
                          "videos": int(group.post_id.nunique()), "comments_without_annotations": int(group["items"].map(len).eq(0).sum()),
                          "comment_weights": weight_summary(group.weight)}
    return pd.DataFrame(support), summary


def validation_diagnostics(gold: pd.DataFrame, path: Path, targets: dict, matcher: Matcher) -> tuple[list, list, dict]:
    """Use an existing validation artifact; reject final IDs, stale labels and duplicates."""
    from .learning import classification_metrics
    validation = {row["sample_id"]: row for row in gold.loc[gold.split.eq("validation")].to_dict("records")}
    predictions = read_csv(path)
    if not predictions.split.eq("validation").all() or not set(predictions.sample_id) <= set(validation):
        raise ValueError("Predicciones fuera de validación; prueba final protegida")
    if predictions.duplicated(["sample_id", "target_id"]).any():
        raise ValueError("Pares de validación duplicados")
    pairs = {}
    for record in predictions.to_dict("records"):
        reference = validation[record["sample_id"]]
        annotations = {item["target_id"]: item["valence"] for item in reference["items"]}
        if (record["comment_id"] != reference["comment_id"] or record["post_id"] != reference["post_id"]
            or record["label"] != annotations.get(record["target_id"], "not_evaluable")
            or record["target_group"] != targets[record["target_id"]]["target_group"]
            or not math.isclose(float(record["weight"]), reference["weight"], rel_tol=1e-10)):
            raise ValueError("Predicción incompatible con la referencia de desarrollo")
        if record["accepted"].lower() not in ("true", "false", "1", "0") or record["context_windowed"].lower() not in ("true", "false", "1", "0"):
            raise ValueError("Indicador booleano inválido")
        pairs[(record["sample_id"], record["target_id"])] = record
    expected = {(row["sample_id"], match["target_id"]) for row in validation.values()
                for match in matcher.find(row["text"], row["comment_published_at"])}
    if set(pairs) != expected:
        raise ValueError("Predicciones incompletas o incompatibles con el extractor congelado")
    units = []
    for record in validation.values():
        for item in record["items"]:
            if item["valence"] not in LABELS[:3]:
                continue
            predicted = pairs.get((record["sample_id"], item["target_id"]))
            status = ("missed_target" if predicted is None else "incomplete_context" if predicted["context_windowed"].lower() in ("true", "1")
                      else "accepted" if predicted["accepted"].lower() in ("true", "1") else "low_confidence")
            units.append({"target_id": item["target_id"], "target_group": target_group(item["target_id"], targets),
                          "valence": item["valence"], "party": record["party"], "comment_type": record["comment_type"],
                          "target_count": "single" if len(record["items"]) == 1 else "multiple", "weight": record["weight"],
                          "status": status, "correct_accepted": bool(predicted and status == "accepted" and predicted["valence"] == item["valence"])})
    frame = pd.DataFrame(units, columns=["target_id", "target_group", "valence", "party", "comment_type", "target_count", "weight", "status", "correct_accepted"])
    breakdown = []
    scopes = [("all", "all", frame)]
    for dimension in ("target_id", "target_group", "valence", "party", "comment_type", "target_count"):
        scopes.extend((dimension, value, group) for value, group in frame.groupby(dimension))
    for dimension, value, group in scopes:
        denominator = float(group.weight.sum())
        for status in STATUSES:
            selected = group.loc[group.status.eq(status)]
            breakdown.append({"dimension": dimension, "value": value, "status": status, "units": len(selected),
                              "denominator_units": len(group), "weighted_share": float(selected.weight.sum()) / denominator if denominator else 0,
                              "denominator_weight": denominator, "correct_accepted_units": int(selected.correct_accepted.sum()),
                              "correct_accepted_weight": float(selected.loc[selected.correct_accepted, "weight"].sum()),
                              "low_support_under_10": len(group) < 10})
    weights = predictions.weight.astype(float)
    raw = classification_metrics(predictions.label, predictions.valence, weights)
    unweighted = classification_metrics(predictions.label, predictions.valence)
    metrics = {"macro_f1_weighted": raw["macro_f1"], "macro_f1_unweighted": unweighted["macro_f1"],
               "pair_weights": weight_summary(weights), "validation_pairs": len(predictions),
               "coverage_all_evaluable_targets": next(row["weighted_share"] for row in breakdown if row["dimension"] == "all" and row["status"] == "accepted")}
    performance = []
    for dimension in ("target_group", "target_id", "comment_type", "party"):
        for value, group in predictions.groupby(dimension):
            scores = classification_metrics(group.label, group.valence, group.weight.astype(float))
            for label, values in scores["classes"].items():
                performance.append({"dimension": dimension, "value": value, "valence": label,
                                    **values, "low_support_under_10": values["support"] < 10,
                                    "macro_f1_three_classes": scores["macro_f1"]})
    metrics["performance_slices"] = performance
    confusion = []
    for (truth, predicted), group in predictions.groupby(["label", "valence"]):
        confusion.append({"truth": truth, "prediction": predicted, "pairs": len(group), "weighted_pairs": float(group.weight.astype(float).sum())})
    return breakdown, confusion, metrics


def protected_files(settings: dict, run: Path) -> dict:
    files = [settings["registry"], settings["_config_path"], settings["source_config"],
             settings["_root"] / "AGENTS.md", settings["_root"] / "docs/doc.tex"]
    files.extend(run.glob("*.csv"))
    files.extend(run.glob("*.json"))
    files.extend(Path(__file__).parent.glob("*.py"))
    for name in ("annotations", "model", "experiments"):
        files.extend(path for path in (run / name).rglob("*") if path.is_file())
    return {str(path.resolve()): sha256(path) for path in sorted(set(files)) if path.is_file()}


def _write_report(output: Path, result: dict) -> None:
    main = result["corpora"]["main"]
    potential = result["primary_opportunity"]
    lines = ["# Auditoría de suficiencia y sesgos", "", "Diagnóstico local; no mide polarización ni habilita inferencia de producción.", "",
             f"Corpus principal: **{main['rows']:,} comentarios**, {main['identified_users']:,} usuarios identificados y {main['videos']:,} videos.",
             f"Cinco canales concentran {main['top5_channels_share']:.2%}; {main['single_comment_users']:,} usuarios tienen un solo comentario.",
             f"Menciones explícitas a bloques conocidos: {main['known_political_candidate_comments']:,} comentarios.", "",
             "## Viabilidad individual", "",
             f"Con las particiones y mínimos actuales hay **{potential['potentially_paired']:,} usuarios potencialmente comparables** de {main['identified_users']:,} identificados ({potential['potentially_paired'] / main['identified_users'] if main['identified_users'] else 0:.2%}).",
             f"Asignación estructural posible: {potential['assignment_possible']:,}; evaluación estructural posible: {potential['evaluation_possible']:,}.",
             "Es un techo condicionado al registro explícito congelado: supone que las menciones podrían resultar evaluables y que existirían los positivos necesarios. No comprueba afinidad, cobertura predictiva ni actitudes reales. Las omisiones del extractor también limitan este marco.", "",
             "## Referencia humana disponible", "",
             "| Partición | Comentarios | Usuarios | Usuarios con un comentario |", "|---|---:|---:|---:|"]
    for split, info in result["annotations"].items():
        lines.append(f"| {split} | {info['comments']} | {info['users']} | {info['single_comment_users']} |")
    reviewed = result["reviewed_development_opportunity"]
    lines += ["", f"Dentro del desarrollo humano principal hay **{reviewed['potentially_paired']} usuarios potencialmente comparables** con la partición A/B actual. La muestra por comentario no sustituye la comprobación de la medida por usuario."]
    lines += ["", "Soportes por clase, actor, bloque, fuente y tipo en annotation_support.csv. Menos de diez unidades es una alerta descriptiva, no un nuevo umbral de aprobación.",
              "La referencia fue asistida por IA y confirmada por un único humano. Desarrollo reutilizado, sin evaluación independiente ni acuerdo entre humanos.", "",
              "## Clasificación y cobertura de desarrollo", "",
              "| Modelo | F1 ponderado | F1 sin ponderar | Cobertura de objetivos evaluables | N efectivo por pesos |", "|---|---:|---:|---:|---:|"]
    for model, metrics in result["models"].items():
        lines.append(f"| {model} | {metrics['macro_f1_weighted']:.4f} | {metrics['macro_f1_unweighted']:.4f} | {metrics['coverage_all_evaluable_targets']:.2%} | {metrics['pair_weights']['effective_n_weights_only']:.1f} |")
    lines += ["", "La cobertura incluye los objetivos omitidos. Desgloses de cobertura en validation_coverage.csv; rendimiento por actor, bloque, fuente y tipo en validation_performance.csv; confusiones globales en validation_confusion.csv. N efectivo considera solo dispersión de pesos; no incorpora dependencia por video, usuario o canal.",
              "No atribuir causalmente el rendimiento a una sola carencia ni interpretar abstención como neutralidad.", "",
              "## Carencias prioritarias", "", "Bloque/clase de validación con menos de diez unidades humanas:", ""]
    for row in result["recommendation"]["low_support_validation_block_valence"]:
        lines.append(f"- {row['value']} / {row['valence']}: {row['units']} unidades.")
    if not result["recommendation"]["low_support_validation_block_valence"]:
        lines.append("No hay celdas observadas por debajo de diez; comprobar también las celdas vacías.")
    if "coverage_by_target_group" in result["recommendation"]:
        lines += ["", "Cobertura por bloque del modelo de referencia diagnóstica (mayor F1 existente, sin selección para producción):", "",
                  "| Bloque del objetivo | Unidades evaluables | Cobertura ponderada |", "|---|---:|---:|"]
        for row in result["recommendation"]["coverage_by_target_group"]:
            lines.append(f"| {row['value']} | {row['denominator_units']} | {row['weighted_share']:.2%} |")
    lines += ["", "Objetivos unknown quedan fuera de AP; los indicadores globales del clasificador también incluyen esos objetivos. Las diferencias entre bloques con soportes distintos son diagnósticas, no pruebas de sesgo sistemático.", "",
              "## Decisión y cierre", "", result["recommendation"]["text"], "",
              "1. Dimensionar la comprobación humana por usuario según disponibilidad, precisión deseada y presupuesto; reutilizar decisiones compatibles de desarrollo. No seleccionar por polarización prevista ni usar etiquetas finales.",
              "2. Priorizar carencias documentadas en annotation_support.csv y validation_coverage.csv, distinguiendo alias, valencia y abstención. No modificar el registro congelado ni iniciar entrenamiento automáticamente.",
              "3. Si la comprobación humana reduce mucho la cobertura o deja incertidumbre excesiva, reconsiderar el alcance individual; una alternativa agregada requiere su propia justificación y validación.", "",
              "La auditoría no fija un tamaño de anotación arbitrario ni garantiza un hallazgo afirmativo. La suficiencia estadística no se decide solo por el número de usuarios potenciales.", "",
              "## Conservación y denominadores", "",
              "Panel separado en panel_composition.csv y summary.json; no se combina con el corpus principal. No observar una valoración externa no equivale a indiferencia. Fuente editorial party y bloque del objetivo siguen siendo variables distintas.",
              f"Los {result['reference']['comments_by_split'].get('test', 0)} finales permanecen reservados: solo se comprueba metadata de partición, nunca se decodifican sus anotaciones para esta auditoría. Los textos del corpus se usan exclusivamente para coincidencias del registro, sin evaluar ni exportar ejemplos de prueba.",
              "Los CSV de oportunidad contienen identificadores locales, sin etiquetas afectivas. Las sensibilidades de partición no se eligen por producir mayor polarización. No hay resultados AP, publicaciones remotas, cambios de umbrales, manuscrito ni contexto productivo.",
              "Procedencia, integridad y hashes de artefactos en manifest.json y protected_inputs.json.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def diagnose_data(settings: dict, run: Path, diagnostic_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", diagnostic_id):
        raise ValueError("diagnostic-id inválido")
    output = settings["outputs"] / run.name / "diagnostics" / diagnostic_id
    if output.exists():
        raise FileExistsError(f"No se sobrescribe la auditoría existente: {output}")
    if (run / "model/test_opened.json").exists():
        raise ValueError("Esta auditoría requiere prueba final todavía reservada")
    manifest = json.loads((run / "annotations/manifest.json").read_text())
    if (sha256(run / "annotations/gold.csv") != manifest["gold_sha256"]
        or sha256(run / "corpus_main.csv") != manifest["corpus_main_sha256"]
        or registry_fingerprint(settings["registry"]) != manifest["registry_sha256"]):
        raise ValueError("Corpus, referencia o registro modificados")
    registry = load_registry(settings["registry"], frozen=True)
    targets = {target["target_id"]: target for target in registry["targets"]}
    gold, reference = load_development(run)
    print("Verificando conservación de datos, modelos y resultados existentes", flush=True)
    before = protected_files(settings, run)
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "manifest.json", {"status": "running", "created_at": stamp()})
    try:
        atomic_json(output / "protected_inputs.json", before)
        result = {"method": "targeted-data-diagnostics-v1", "reference": reference, "corpora": {}, "models": {}}
        matcher = Matcher(registry)
        for corpus in ("main", "panel"):
            path = run / f"corpus_{corpus}.csv"
            if not path.exists():
                continue
            info, events, distribution, actors = composition(path, matcher, corpus)
            users = info.pop("user_comment_counts")
            info.pop("actors")
            result["corpora"][corpus] = info
            distribution.to_csv(output / f"{corpus}_composition.csv", index=False)
            actors.to_csv(output / f"{corpus}_actors.csv", index=False)
            if corpus != "main":
                continue
            sensitivity = []
            for seed, reverse in [(settings["seed"], False), (settings["seed"], True), *[(seed, False) for seed in range(43, 53) if seed != settings["seed"]]]:
                table = opportunities(events, users, settings, seed=seed, reverse=reverse)
                counts = {key: int(table[key].sum()) for key in ("assignment_possible", "both_blocks_evaluation", "evaluation_possible", "potentially_paired")}
                sensitivity.append({"seed": seed, "reverse": reverse, **counts})
                if seed == settings["seed"] and not reverse:
                    result["primary_opportunity"] = counts
                    table.to_csv(output / "user_opportunity.csv", index=False)
                    activity = [{"minimum_total_comments": threshold, "users": int(table.total_comments.ge(threshold).sum()),
                                 "potentially_paired": int((table.total_comments.ge(threshold) & table.potentially_paired).sum())}
                                for threshold in (1, 3, 5, 10, 20)]
                    pd.DataFrame(activity).to_csv(output / "opportunity_activity.csv", index=False)
            pd.DataFrame(sensitivity).to_csv(output / "opportunity_partitions.csv", index=False)
        support, result["annotations"] = annotation_support(gold, targets)
        support.to_csv(output / "annotation_support.csv", index=False)
        reviewed = gold.loc[gold.corpus.eq("main") & gold.user_id.ne("")]
        reviewed_events = []
        for record in reviewed.to_dict("records"):
            groups = {target_group(item["target_id"], targets) for item in record["items"]} & set(POLITICAL)
            reviewed_events.extend({**{key: record.get(key, "") for key in EVENT_COLUMNS}, "target_group": group} for group in sorted(groups))
        reviewed_table = opportunities(pd.DataFrame(reviewed_events, columns=EVENT_COLUMNS), Counter(reviewed.user_id), settings, seed=settings["seed"])
        result["reviewed_development_opportunity"] = {"users": len(reviewed_table), "potentially_paired": int(reviewed_table.potentially_paired.sum())}
        coverage, confusion, performance = [], [], []
        for path in sorted((run / "experiments").glob("*/finalists/*/validation_predictions.csv")):
            source = json.loads((path.parents[2] / "source.json").read_text())
            if source["registry_sha256"] != sha256(settings["registry"]) or source["study_gold_sha256"] != manifest.get("study_gold_sha256", manifest["gold_sha256"]):
                raise ValueError("Experimento incompatible con la referencia actual")
            model = f"{path.parents[2].name}/{path.parent.name}"
            parts, errors, metrics = validation_diagnostics(gold, path, targets, matcher)
            performance.extend({"model": model, **row} for row in metrics.pop("performance_slices"))
            result["models"][model] = metrics
            coverage.extend({"model": model, **row} for row in parts)
            confusion.extend({"model": model, **row} for row in errors)
        pd.DataFrame(coverage).to_csv(output / "validation_coverage.csv", index=False)
        pd.DataFrame(confusion).to_csv(output / "validation_confusion.csv", index=False)
        pd.DataFrame(performance).to_csv(output / "validation_performance.csv", index=False)
        possible = result["primary_opportunity"]["potentially_paired"]
        result["recommendation"] = {"status": "design_user_validation" if possible else "insufficient_structural_opportunity",
            "text": (f"Hay {possible:,} usuarios potencialmente comparables en el marco explícito. Prioridad: diseñar una comprobación humana por usuario y dimensionar su coste antes de otro entrenamiento. Este número no demuestra suficiencia estadística ni polarización."
                     if possible else "Ningún usuario satisface siquiera el techo estructural actual. Prioridad: precisar datos faltantes y viabilidad de recuperación mediante YouTube; si no puede sostenerse la medición individual, justificar una alternativa agregada.")}
        if result["models"]:
            reference_model = max(sorted(result["models"]), key=lambda key: result["models"][key]["macro_f1_weighted"])
            result["recommendation"]["reference_model_for_diagnosis_only"] = reference_model
            result["recommendation"]["coverage_by_target_group"] = [row for row in coverage
                if row["model"] == reference_model and row["dimension"] == "target_group" and row["status"] == "accepted"]
        result["recommendation"]["low_support_validation_block_valence"] = support.loc[
            support.dimension.eq("target_group_valence") & support.split.eq("validation")
            & support.value.isin(POLITICAL) & support.low_support_under_10].to_dict("records") if not support.empty else []
        atomic_json(output / "decision.json", result["recommendation"])
        after = protected_files(settings, run)
        if before != after or (run / "model/test_opened.json").exists():
            raise ValueError("Cambió un archivo protegido durante la auditoría")
        atomic_json(output / "summary.json", result)
        _write_report(output, result)
        artifacts = {path.name: sha256(path) for path in sorted(output.iterdir()) if path.name != "manifest.json"}
        atomic_json(output / "manifest.json", {"status": "complete", "created_at": stamp(), "method": result["method"],
                    "run_id": run.name, "diagnostic_id": diagnostic_id, "test_evaluated": False, "test_labels_decoded": False,
                    "production_analysis": False, "protected_files_unchanged": len(before), "artifacts": artifacts,
                    "reference_limitation": manifest.get("annotation_limitation"), "sampling_probability_scope": manifest.get("sampling_probability_scope")})
    except Exception as error:
        atomic_json(output / "manifest.json", {"status": "failed", "created_at": stamp(), "error": str(error), "test_evaluated": False})
        raise
    return output
