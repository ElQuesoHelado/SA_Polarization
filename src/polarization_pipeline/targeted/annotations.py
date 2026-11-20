from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import LABELS, atomic_json, read_csv, require_columns, sha256, stamp
from .registry import Matcher, load_registry, normalized, registry_fingerprint


def text_key(text: str) -> str:
    return " ".join(normalized(text).split())


def split_for_video(video_id: str, seed: int) -> str:
    value = int(hashlib.sha256(f"model:{seed}:{video_id}".encode()).hexdigest()[:12], 16) % 100
    return "train" if value < 60 else "validation" if value < 75 else "test"


def development_split_for_video(video_id: str, seed: int) -> str:
    value = int(hashlib.sha256(f"model:{seed}:{video_id}".encode()).hexdigest()[:12], 16) % 100
    return "train" if value < 80 else "validation"


def stratified_sample(frame: pd.DataFrame, size: int, seed: int) -> pd.DataFrame:
    if len(frame) < size:
        raise ValueError(f"Muestra insuficiente: se requieren {size} comentarios y hay {len(frame)}. Completa el panel antes de exportar.")
    groups = list(frame.groupby(["party", "month", "enrichment"], sort=True))
    populations = np.array([len(group) for _, group in groups])
    # Half proportional allocation, half enriched strata; fixed-size, without replacement.
    enrichment = np.array([3.0 if key[2] != "none" else 1.0 for key, _ in groups])
    desired = size * (0.5 * populations / populations.sum() + 0.5 * enrichment / enrichment.sum())
    counts = np.minimum(np.floor(desired).astype(int), populations)
    while counts.sum() < size:
        priorities = np.where(counts < populations, desired - counts, -np.inf)
        counts[int(np.argmax(priorities))] += 1
    selected = []
    for (_, group), count, population in zip(groups, counts, populations):
        if count:
            sample = group.sample(n=int(count), random_state=seed).copy()
            sample["sampling_probability"] = count / population
            selected.append(sample)
    return pd.concat(selected, ignore_index=True)


def export_annotations(settings: dict, run: Path, *, refresh_unreviewed: bool = False,
                       exclude_test_sample: pd.DataFrame | None = None) -> Path:
    folder = run / "annotations"
    if folder.exists():
        if not refresh_unreviewed:
            raise FileExistsError(f"Ya existe {folder}; no se sobrescriben anotaciones")
        if (folder / "gold.csv").exists() or (run / "model").exists():
            raise ValueError("No se puede regenerar una muestra adjudicada o utilizada para entrenar")
        if (folder / "assisted_manifest.json").exists():
            raise ValueError("Ya existe trabajo asistido; conservarlo y crear otra ejecución")
        for reviewer in (1, 2):
            previous = read_csv(folder / f"reviewer_{reviewer}.csv")
            if previous.review_complete.str.strip().ne("").any() or previous.annotation_json.str.strip().ne("").any():
                raise ValueError("Ya hay trabajo humano en los formularios; conservarlo y crear otra ejecución")
    registry = load_registry(settings["registry"])
    matcher = Matcher(registry)
    main = read_csv(run / "corpus_main.csv")
    panel_path = run / "corpus_panel.csv"
    panel = read_csv(panel_path) if panel_path.exists() else pd.DataFrame()
    replies = panel.loc[panel.comment_type.eq("reply")] if not panel.empty else pd.DataFrame(columns=main.columns)
    pool = pd.concat([main, replies], ignore_index=True).fillna("")
    pool = pool.loc[pool.comment_id.ne("") & pool.text.str.strip().ne("")].drop_duplicates("comment_id")
    pool["text_key"] = pool.text.map(text_key)
    pool = pool.drop_duplicates("text_key").copy()
    split_seed = settings.get("sampling_split_seed", settings["seed"])
    pool["split"] = pool.post_id.map(lambda video: split_for_video(video, split_seed))
    if exclude_test_sample is not None:
        previous_videos = set(exclude_test_sample.post_id)
        previous_texts = {text_key(text) for text in exclude_test_sample.text}
        if settings.get("reuse_reviewed_development"):
            # Previously seen videos are development-only, with an 80/20 split.
            seen = pool.post_id.isin(previous_videos)
            pool.loc[seen, "split"] = pool.loc[seen, "post_id"].map(lambda video: development_split_for_video(video, split_seed))
        eligible = ~pool.post_id.isin(previous_videos) & ~pool.text_key.isin(previous_texts)
        pool = pool.loc[pool.split.ne("test") | eligible].copy()
    pool["month"] = pd.to_datetime(pool.comment_published_at, utc=True).dt.strftime("%Y-%m")
    def enrich(row):
        matches = matcher.find(row["text"], row["comment_published_at"])
        return "candidate_positive" if matches and row.get("sentimiento") == "positive" else "candidate" if matches else "none"
    pool["enrichment"] = [enrich(dict(zip(pool.columns, values))) for values in pool.itertuples(index=False, name=None)]
    total = settings["annotation_comments"]
    n_replies = settings["annotation_replies"]
    split_counts = {"train": int(total * 0.60), "validation": int(total * 0.15)}
    split_counts["test"] = total - sum(split_counts.values())
    selections = []
    for split, n in split_counts.items():
        nr = round(n_replies * n / total)
        for kind, count in (("reply", nr), ("top_level", n - nr)):
            subset = pool.loc[pool.split.eq(split) & pool.comment_type.eq(kind)]
            if exclude_test_sample is not None and settings.get("reuse_reviewed_development") and split != "test":
                prior = subset.loc[subset.comment_id.isin(set(exclude_test_sample.comment_id))]
                reuse_count = min(count, len(prior))
                if reuse_count:
                    selected = stratified_sample(prior, reuse_count, settings["seed"])
                    prior_pi = exclude_test_sample.set_index("comment_id").sampling_probability.astype(float)
                    selected["source_sampling_probability"] = selected.comment_id.map(prior_pi)
                    selected["sampling_probability"] *= selected.source_sampling_probability
                    selected["development_selection"] = "previous_reviewed_frame"
                    selections.append(selected)
                if reuse_count < count:
                    selected = stratified_sample(subset.loc[~subset.comment_id.isin(set(exclude_test_sample.comment_id))], count - reuse_count, settings["seed"])
                    selected["development_selection"] = "new_frame_fill"
                    selections.append(selected)
            else:
                selected = stratified_sample(subset, count, settings["seed"])
                selected["development_selection"] = "fresh_test" if exclude_test_sample is not None else "original_frame"
                selections.append(selected)
    sample = pd.concat(selections, ignore_index=True).sample(frac=1, random_state=settings["seed"]).reset_index(drop=True)
    sample["sample_id"] = sample.comment_id.map(lambda x: hashlib.sha256(f"annotation:{x}".encode()).hexdigest()[:20])
    train_ids = sample.index[sample.split.eq("train")][:200]
    sample["pilot"] = False
    sample.loc[train_ids, "pilot"] = True
    if folder.exists():
        from uuid import uuid4
        backup = run / ("annotations_unreviewed_backup_" + uuid4().hex[:12])
        folder.rename(backup)
        print(f"Formularios anteriores sin revisar conservados en {backup}")
    folder.mkdir()
    sample.to_csv(folder / "sampling_manifest.csv", index=False)
    blind = sample[["sample_id", "comment_id", "text", "parent_text", "post_title", "pilot"]].copy()
    blind["annotation_json"] = ""
    blind["review_complete"] = ""
    for reviewer in ("reviewer_1", "reviewer_2"):
        blind.to_csv(folder / f"{reviewer}.csv", index=False)
    atomic_json(folder / "manifest.json", {
        "created_at": stamp(), "registry_sha256": registry_fingerprint(settings["registry"]),
        "sampling_sha256": sha256(folder / "sampling_manifest.csv"),
        "corpus_main_sha256": sha256(run / "corpus_main.csv"),
        "rows": len(sample), "splits": sample.split.value_counts().to_dict(),
        "status": "awaiting_two_human_reviewers", "registry_status": registry["status"],
        "model_test_opened": False,
        "sampling_split_seed": split_seed,
        "sampling_probability_scope": "Prueba: dentro de estrato y partición de videos/textos no revisados. Desarrollo reutilizado: probabilidad original por selección condicional en el marco revisado; no es evaluación independiente del corpus.",
        "reuse_reviewed_development": bool(settings.get("reuse_reviewed_development")),
    })
    return folder


def parse_review(path: Path, sample: pd.DataFrame, targets: set[str], *, allow_extra: bool = False) -> dict:
    frame = read_csv(path)
    require_columns(frame, ["sample_id", "comment_id", "text", "annotation_json", "review_complete"])
    if allow_extra:
        frame = frame.loc[frame.sample_id.isin(sample.sample_id)]
    if frame.sample_id.duplicated().any() or set(frame.sample_id) != set(sample.sample_id):
        raise ValueError(f"{path.name}: IDs duplicados, faltantes o ajenos a la muestra")
    expected = sample.set_index("sample_id")
    records = {}
    for row in frame.to_dict("records"):
        original = expected.loc[row["sample_id"]]
        if row["text"] != original["text"] or row["comment_id"] != original["comment_id"]:
            raise ValueError(f"{path.name}: texto o identificador editado")
        if row["review_complete"].lower() not in ("true", "1", "yes", "si", "sí"):
            raise ValueError(f"{path.name}: revisión incompleta; no se permiten etiquetas sintéticas")
        try:
            items = json.loads(row["annotation_json"])
        except (ValueError, TypeError):
            raise ValueError(f"{path.name}: annotation_json inválido") from None
        records[row["sample_id"]] = validate_items(items, row["text"], targets)
    return records


def validate_items(items: list, text: str, targets: set[str]) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("annotation_json debe ser una lista; [] expresa ausencia de objetivos evaluables")
    seen, cleaned = set(), []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Cada anotación debe ser un objeto JSON")
        target_id = item.get("target_id")
        if not isinstance(target_id, str) or not target_id or target_id in seen or (target_id not in targets and (not target_id.startswith("unregistered:") or not target_id.split(":", 1)[1].strip())):
            raise ValueError("Objetivo inválido o repetido; usa unregistered:nombre para un objetivo omitido")
        if item.get("valence") not in LABELS:
            raise ValueError("Valencia inválida")
        start, end = item.get("mention_start"), item.get("mention_end")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError("El objetivo explícito requiere offsets válidos en el comentario")
        seen.add(target_id)
        cleaned.append({"target_id": target_id, "valence": item["valence"], "mention_start": start, "mention_end": end})
    return sorted(cleaned, key=lambda x: x["target_id"])


def cohen_kappa(left: list[str], right: list[str]) -> float | None:
    if not left:
        return None
    labels = sorted(set(left) | set(right))
    observed = np.mean(np.array(left) == np.array(right))
    expected = sum(left.count(label) * right.count(label) for label in labels) / len(left) ** 2
    return float((observed - expected) / (1 - expected)) if expected < 1 else None


def import_annotations(settings: dict, run: Path, *, pilot_only: bool = False) -> None:
    folder = run / "annotations"
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest.get("annotation_protocol") == "ai_assisted_single_human_v1":
        raise ValueError("Esta ejecución usa revisión asistida; utiliza assisted-import")
    if manifest["registry_sha256"] != registry_fingerprint(settings["registry"]):
        raise ValueError("El registro cambió después del muestreo; audita y genera otra muestra")
    if manifest["sampling_sha256"] != sha256(folder / "sampling_manifest.csv"):
        raise ValueError("El manifiesto de muestreo fue alterado")
    sample = read_csv(folder / "sampling_manifest.csv")
    if pilot_only:
        sample = sample.loc[sample.pilot.str.lower().eq("true")]
    registry = load_registry(settings["registry"], frozen=True)
    targets = {item["target_id"] for item in registry["targets"]}
    left = parse_review(folder / "reviewer_1.csv", sample, targets, allow_extra=pilot_only)
    right = parse_review(folder / "reviewer_2.csv", sample, targets, allow_extra=pilot_only)
    a, b, detection_a, detection_b, disagreements = [], [], [], [], []
    for row in sample.to_dict("records"):
        sample_id = row["sample_id"]
        l = {x["target_id"]: x["valence"] for x in left[sample_id]}
        r = {x["target_id"]: x["valence"] for x in right[sample_id]}
        for target in set(l) | set(r):
            detection_a.append(target in l)
            detection_b.append(target in r)
            # No agreement credit for the huge set of absent targets.
            a.append(l.get(target, "absent"))
            b.append(r.get(target, "absent"))
        if left[sample_id] != right[sample_id]:
            disagreements.append({"sample_id": sample_id, "left_json": json.dumps(left[sample_id], ensure_ascii=False),
                                  "right_json": json.dumps(right[sample_id], ensure_ascii=False), "annotation_json": "", "review_complete": ""})
    kappa = cohen_kappa(a, b)
    atomic_json(folder / ("pilot_agreement.json" if pilot_only else "agreement.json"), {"kappa": kappa, "annotation_units": len(a), "disagreements": len(disagreements),
                "target_presence_agreement": float(np.mean(np.array(detection_a) == np.array(detection_b))) if detection_a else None})
    if kappa is None or kappa < settings["quality"]["kappa"]:
        raise ValueError("Acuerdo insuficiente; revisar código y repetir piloto antes de adjudicar")
    if pilot_only:
        print("Piloto con acuerdo suficiente; completar las revisiones restantes antes de importar el conjunto completo.")
        return
    if disagreements:
        adjudication = folder / "adjudication.csv"
        if not adjudication.exists():
            pd.DataFrame(disagreements).to_csv(adjudication, index=False)
            raise ValueError(f"Hay {len(disagreements)} desacuerdos; completar {adjudication} y reimportar")
        # Adjudicators use the same validation contract as reviewers.
        adjudicated = read_csv(adjudication)
        required_ids = {row["sample_id"] for row in disagreements}
        selected = sample.loc[sample.sample_id.isin(required_ids)]
        adjudicated = adjudicated.merge(selected[["sample_id", "text", "comment_id"]], on="sample_id", validate="one_to_one")
        temporary = folder / ".adjudication_validation.csv"
        try:
            adjudicated.to_csv(temporary, index=False)
            fixes = parse_review(temporary, selected, targets)
        finally:
            temporary.unlink(missing_ok=True)
        left.update(fixes)
    gold = sample.copy()
    gold["annotation_json"] = [json.dumps(left[x], ensure_ascii=False) for x in gold.sample_id]
    gold.to_csv(folder / "gold.csv", index=False)
    manifest.update(status="adjudicated", imported_at=stamp(), gold_sha256=sha256(folder / "gold.csv"))
    atomic_json(folder / "manifest.json", manifest)


def check_development_extraction(settings: dict, gold: pd.DataFrame) -> None:
    matcher = Matcher(load_registry(settings["registry"]))
    for split in ("train", "validation"):
        tp = fp = fn = 0.0
        for row in gold.loc[gold.split.eq(split)].to_dict("records"):
            expected = {x["target_id"] for x in json.loads(row["annotation_json"])}
            found = {x["target_id"] for x in matcher.find(row["text"], row["comment_published_at"])}
            weight = 1 / float(row["sampling_probability"])
            tp += weight * len(found & expected)
            fp += weight * len(found - expected)
            fn += weight * len(expected - found)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        if precision < settings["quality"]["target_precision"] or recall < settings["quality"]["target_recall"]:
            raise ValueError(f"Extracción insuficiente en {split}: precisión={precision:.3f}, recall={recall:.3f}; no entrenar ni abrir prueba final")


def training_pairs(settings: dict, run: Path) -> pd.DataFrame:
    registry = load_registry(settings["registry"], frozen=True)
    manifest = json.loads((run / "annotations" / "manifest.json").read_text())
    if manifest.get("annotation_protocol") == "ai_assisted_single_human_v1":
        if manifest.get("status") != "human_reviewed_assisted":
            raise ValueError("Se requiere confirmar humanamente toda la revisión asistida")
        from .assisted import verify_completed
        verify_completed(settings, run)
    elif manifest.get("status") != "adjudicated":
        raise ValueError("Se requieren dos revisiones humanas y adjudicación")
    if manifest.get("corpus_main_sha256") and sha256(run / "corpus_main.csv") != manifest["corpus_main_sha256"]:
        raise ValueError("El corpus cambió después de seleccionar las anotaciones")
    if registry_fingerprint(settings["registry"]) != manifest["registry_sha256"] or sha256(run / "annotations" / "gold.csv") != manifest["gold_sha256"]:
        raise ValueError("Registro o anotaciones cambiaron después de adjudicar")
    matcher = Matcher(registry)
    gold_frame = read_csv(run / "annotations" / "gold.csv")
    if settings.get("method_version") == "targeted-v2":
        check_development_extraction(settings, gold_frame)
    rows = []
    for row in gold_frame.to_dict("records"):
        gold = {x["target_id"]: x for x in json.loads(row["annotation_json"])}
        matches = {x["target_id"]: x for x in matcher.find(row["text"], row["comment_published_at"])}
        # Omitted/unregistered targets remain in evaluation as false negatives, not fake training pairs.
        for target_id, match in matches.items():
            annotation = gold.get(target_id, {"valence": "not_evaluable"})
            rows.append({**row, **match, "label": annotation["valence"], "weight": 1 / float(row["sampling_probability"])})
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("Sin pares entrenables")
    frame.to_csv(run / "training_pairs.csv", index=False)
    return frame
