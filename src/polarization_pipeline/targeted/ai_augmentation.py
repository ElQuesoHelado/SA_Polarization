"""AI-only auxiliary training annotations, with human-only development evaluation."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from .annotations import split_for_video, text_key
from .common import LABELS, atomic_json, read_csv, sha256, stamp
from .diagnostics import load_development, protected_files, validation_diagnostics
from .registry import Matcher, load_registry, registry_fingerprint

PROTOCOL = "targeted-ai-augmentation-v1"
CODES = dict(zip("PN0MX", LABELS))
INPUTS = ("sample.csv", "sample_manifest.json", "ai_annotations.json", "human_development.csv", "human_pairs.csv", "augmented_pairs.csv", "training_config.toml")


def validate_plan(plan):
    expected = {"protocol": PROTOCOL, "sample_comments": 2000, "sampling_seed": 57, "ai_weight": .25,
        "maximum_fits": 3, "final_seeds": [42, 43, 44], "learning_rates": [1e-5], "objectives": ["ai_augmented"],
        "maximum_epochs": 8, "patience": 2, "effective_batch_size": 16, "weight_decay": .01, "gradient_clip": 1.0,
        "quotas": {"left_only": 800, "right_only": 600, "both_blocks": 400, "unknown_only": 200}}
    if any(plan.get(key) != value for key, value in expected.items()):
        raise ValueError("La ampliación IA debe conservar el protocolo y presupuesto congelados")
    models = plan.get("models", [])
    if len(models) != 1 or models[0] != {"id": "beto_ai_augmented", "model": "dccuchile/bert-base-spanish-wwm-uncased",
        "revision": "d1c9c4565c9d6731e57ed7f027b802697bad861e", "maximum_tokens": 512, "physical_batch_size": 4}:
        raise ValueError("La ampliación IA solo admite el BETO de referencia")


def balanced_sample(frame, size, seed):
    groups = list(frame.groupby(["channel_id", "month"], sort=True))
    populations = np.array([len(group) for _, group in groups])
    if populations.sum() < size:
        raise ValueError("Estrato insuficiente; no sustituir cuotas silenciosamente")
    desired = size * (.5 * populations / populations.sum() + .5 / len(groups))
    counts = np.minimum(np.floor(desired).astype(int), populations)
    while counts.sum() < size:
        counts[np.argmax(np.where(counts < populations, desired - counts, -np.inf))] += 1
    return pd.concat([group.sample(n=int(count), random_state=seed) for (_, group), count in zip(groups, counts) if count])


def export_sample(settings, run, experiment_id, training_config):
    from .development import experiment_directory
    root = experiment_directory(run, experiment_id)
    if root.exists():
        raise FileExistsError("La muestra IA ya existe; reanudar anotación sin regenerarla")
    training_config = Path(training_config)
    if not training_config.is_absolute():
        training_config = settings["_root"] / training_config
    plan = tomllib.loads(training_config.read_text())
    validate_plan(plan)
    manifest = json.loads((run / "annotations/manifest.json").read_text())
    if (manifest.get("status") != "human_reviewed_assisted" or (run / "model/test_opened.json").exists()
        or sha256(run / "annotations/gold.csv") != manifest["gold_sha256"]
        or sha256(run / "corpus_main.csv") != manifest["corpus_main_sha256"]
        or registry_fingerprint(settings["registry"]) != manifest["registry_sha256"]):
        raise ValueError("Se requiere referencia humana cerrada, inmutable y prueba reservada")
    registry = load_registry(settings["registry"], frozen=True)
    matcher = Matcher(registry)
    old_users, old_videos, old_texts = set(), set(), set()
    previous = [run, settings["workspace"] / "targeted_20261114"]
    for original in dict.fromkeys(previous):
        path = original / "annotations/sampling_manifest.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                old_users.add(row["user_id"]); old_videos.add(row["post_id"]); old_texts.add(text_key(row["text"]))
    rows, seen = [], set()
    with (run / "corpus_main.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (not row["user_id"] or row["user_id"] in old_users or row["post_id"] in old_videos
                or split_for_video(row["post_id"], settings["sampling_split_seed"]) != "train"):
                continue
            key = text_key(row["text"])
            if key in old_texts or key in seen:
                continue
            matches = matcher.find(row["text"], row["comment_published_at"])
            groups = {match["target_group"] for match in matches}
            political = groups & {"izquierda", "derecha"}
            category = ("both_blocks" if len(political) == 2 else "left_only" if political == {"izquierda"}
                else "right_only" if political == {"derecha"} else "unknown_only" if "unknown" in groups else "")
            if not category:
                continue
            seen.add(key)
            rows.append({**row, "text_key": key, "split": "train", "category": category,
                "month": row["comment_published_at"][:7], "candidates_json": json.dumps(matches, ensure_ascii=False),
                "sample_id": hashlib.sha256(f"ai-augmentation:{row['comment_id']}".encode()).hexdigest()[:20]})
    pool = pd.DataFrame(rows)
    sample = pd.concat([balanced_sample(pool.loc[pool.category.eq(category)], count, plan["sampling_seed"])
        for category, count in plan["quotas"].items()]).sample(frac=1, random_state=plan["sampling_seed"]).reset_index(drop=True)
    human, _ = load_development(run)
    human = human.drop(columns=["items", "weight"])
    pairs = human_pairs(human, matcher)
    protected = {name: digest for name, digest in protected_files(settings, run).items() if "/src/polarization_pipeline/" not in name}
    root.mkdir(parents=True)
    sample.to_csv(root / "sample.csv", index=False)
    human.to_csv(root / "human_development.csv", index=False)
    pairs.to_csv(root / "human_pairs.csv", index=False)
    shutil.copy2(training_config, root / "training_config.toml")
    plan.update(experiment_id=experiment_id, frozen_at=stamp(), training_config_sha256=sha256(training_config))
    atomic_json(root / "plan.json", plan)
    atomic_json(root / "protected_originals.json", protected)
    atomic_json(root / "sample_manifest.json", {"created_at": stamp(), "protocol": PROTOCOL, "human_confirmed": False,
        "sample_sha256": sha256(root / "sample.csv"), "rows": len(sample), "quotas": plan["quotas"],
        "eligible_by_category": pool.category.value_counts().to_dict(), "registry_sha256": sha256(settings["registry"]),
        "study_gold_sha256": manifest["gold_sha256"], "corpus_main_sha256": manifest["corpus_main_sha256"],
        "human_development_sha256": sha256(root / "human_development.csv"), "human_pairs_sha256": sha256(root / "human_pairs.csv"),
        "quality": settings["quality"], "annotation_protocol": manifest["annotation_protocol"],
        "annotation_limitation": manifest["annotation_limitation"], "sampling_probability_scope": manifest["sampling_probability_scope"]})
    atomic_json(root / "ai_annotations.json", {})
    return root


def human_pairs(gold, matcher):
    rows = []
    for row in gold.to_dict("records"):
        if row["split"] not in ("train", "validation"):
            raise ValueError("No incluir prueba final en ampliación IA")
        labels = {item["target_id"]: item["valence"] for item in json.loads(row["annotation_json"])}
        for match in matcher.find(row["text"], row["comment_published_at"]):
            rows.append({**row, **match, "label": labels.get(match["target_id"], "not_evaluable"),
                "weight": 1 / float(row["sampling_probability"]), "label_origin": "human_confirmed"})
    return pd.DataFrame(rows)


def import_annotations(root, batch):
    if (root / "source.json").exists():
        raise ValueError("La ampliación IA ya está congelada para entrenamiento")
    meta = json.loads((root / "sample_manifest.json").read_text())
    if sha256(root / "sample.csv") != meta["sample_sha256"] or batch["sample_sha256"] != meta["sample_sha256"]:
        raise ValueError("Muestra IA alterada o lote de otra muestra")
    if not batch.get("origin", "").strip() or not batch.get("note", "").strip():
        raise ValueError("Falta procedencia o explicación de anotación IA")
    sample = read_csv(root / "sample.csv")
    stored = json.loads((root / "ai_annotations.json").read_text())
    start = batch["start"]
    if type(start) is not int or start < 0 or start + len(batch["labels"]) > len(sample) or not batch["labels"]:
        raise ValueError("Rango de lote inválido")
    for index, codes in enumerate(batch["labels"], start):
        row = sample.iloc[index]
        matches = json.loads(row.candidates_json)
        if len(codes) != len(matches) or any(code not in (*CODES, "U") for code in codes):
            raise ValueError(f"Etiquetas IA incompatibles con los objetivos del índice {index}")
        note = batch.get("notes", {}).get(str(index), batch["note"])
        annotation = {"codes": codes, "origin": batch["origin"], "note": note, "human_confirmed": False}
        if row.sample_id in stored:
            if stored[row.sample_id] != annotation:
                raise ValueError("No sobrescribir una decisión IA ya registrada")
        else:
            stored[row.sample_id] = annotation
    atomic_json(root / "ai_annotations.json", stored)
    return {"annotated": len(stored), "total": len(sample)}


def build_augmented(root):
    sample = read_csv(root / "sample.csv")
    annotations = json.loads((root / "ai_annotations.json").read_text())
    if set(annotations) != set(sample.sample_id):
        raise ValueError("Faltan anotaciones IA; no solicitar confirmaciones humanas")
    rows, excluded = [], 0
    for row in sample.to_dict("records"):
        annotation = annotations[row["sample_id"]]
        if annotation.get("human_confirmed") is not False or not annotation.get("note") or not annotation.get("origin"):
            raise ValueError("Procedencia IA inválida")
        matches = json.loads(row["candidates_json"])
        if len(annotation["codes"]) != len(matches):
            raise ValueError("Anotación IA incompatible")
        for match, code in zip(matches, annotation["codes"]):
            if code == "U":
                excluded += 1
                continue
            if code not in CODES:
                raise ValueError("Etiqueta IA desconocida")
            rows.append({**row, **match, "label": CODES[code], "label_origin": "ai_auxiliary", "weight": 1.0,
                "sampling_probability": 1.0, "annotation_protocol": "ai_only_auxiliary_v1", "annotation_json": "[]"})
    human = read_csv(root / "human_pairs.csv")
    combined = pd.concat([human, pd.DataFrame(rows)], ignore_index=True).fillna("")
    return combined, {"ai_comments": len(sample), "ai_pairs": len(rows), "excluded_uncertain_pairs": excluded}


def freeze(settings, run, experiment_id, training_config):
    from .development import experiment_directory
    root = experiment_directory(run, experiment_id)
    if not root.exists():
        raise ValueError("Primero exportar y anotar la muestra IA")
    plan = json.loads((root / "plan.json").read_text()); validate_plan(plan)
    if sha256(training_config) != plan["training_config_sha256"]:
        raise ValueError("Configuración de ampliación alterada")
    if (root / "source.json").exists():
        verify(settings, run, root)
        return root
    meta = json.loads((root / "sample_manifest.json").read_text())
    if sha256(root / "sample.csv") != meta["sample_sha256"] or sha256(settings["registry"]) != meta["registry_sha256"]:
        raise ValueError("Muestra o registro alterados")
    for name in ("human_development", "human_pairs"):
        if sha256(root / f"{name}.csv") != meta[f"{name}_sha256"]:
            raise ValueError("Referencia humana de desarrollo alterada")
    original = json.loads((run / "annotations/manifest.json").read_text())
    if sha256(run / "annotations/gold.csv") != meta["study_gold_sha256"] or original["gold_sha256"] != meta["study_gold_sha256"]:
        raise ValueError("Gold original alterado")
    pairs, counts = build_augmented(root)
    pairs.to_csv(root / "augmented_pairs.csv", index=False)
    parent = run / "experiments" / plan["parent_experiment_id"] / "finalists/beto"
    baseline = root / "baseline"; baseline.mkdir()
    for name in ("validation_report.json", "validation_predictions.csv"):
        shutil.copy2(parent / name, baseline / name)
    atomic_json(baseline / "manifest.json", {"origin": "frozen_previous_beto", "parent": str(parent),
        "files": {name: sha256(baseline / name) for name in ("validation_report.json", "validation_predictions.csv")}})
    source = {"created_at": stamp(), "study_gold_sha256": meta["study_gold_sha256"], "registry_sha256": meta["registry_sha256"],
        "development_gold_sha256": sha256(root / "human_development.csv"), "annotation_protocol": meta["annotation_protocol"],
        "annotation_limitation": meta["annotation_limitation"] + " Entrenamiento ampliado con etiquetas IA no confirmadas por humanos.",
        "sampling_probability_scope": meta["sampling_probability_scope"], "quality": settings["quality"],
        "plan_sha256": sha256(root / "plan.json"), "counts": counts,
        "input_hashes": {name: sha256(root / name) for name in (*INPUTS, "baseline/manifest.json", "baseline/validation_report.json", "baseline/validation_predictions.csv")}}
    atomic_json(root / "source.json", source)
    verify(settings, run, root)
    return root


def verify(settings, run, root):
    source = json.loads((root / "source.json").read_text()); plan = json.loads((root / "plan.json").read_text())
    validate_plan(plan)
    if source["plan_sha256"] != sha256(root / "plan.json") or source["registry_sha256"] != sha256(settings["registry"]) or source["quality"] != settings["quality"]:
        raise ValueError("Procedencia IA alterada")
    for name, digest in source["input_hashes"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path) != digest:
            raise ValueError("Entrada IA congelada alterada")
    gold = read_csv(root / "human_development.csv")
    if not set(gold.split) <= {"train", "validation"}:
        raise ValueError("Prueba final en desarrollo IA")
    pairs = read_csv(root / "augmented_pairs.csv")
    if not set(pairs.label_origin) <= {"human_confirmed", "ai_auxiliary"} or pairs.loc[pairs.label_origin.eq("ai_auxiliary")].split.ne("train").any():
        raise ValueError("Etiquetas IA fuera de entrenamiento")
    if not pairs.loc[pairs.split.eq("validation")].label_origin.eq("human_confirmed").all():
        raise ValueError("Validación debe ser exclusivamente humana")
    sample = read_csv(root / "sample.csv")
    check_separation(sample, gold)
    expected, _ = build_augmented(root)
    # Compare serialized values to tolerate CSV type inference, never altered labels.
    if pairs.to_csv(index=False) != expected.to_csv(index=False):
        raise ValueError("Pares ampliados incompatibles con las anotaciones de origen")
    return gold, pairs


def check_separation(sample, human):
    if not sample.split.eq("train").all() or sample.sample_id.duplicated().any() or sample.comment_id.duplicated().any():
        raise ValueError("Muestra IA duplicada o fuera de entrenamiento")
    for column in ("sample_id", "comment_id", "post_id", "user_id"):
        if set(sample[column]) & set(human[column]):
            raise ValueError(f"Muestra IA comparte {column} con referencia humana")
    if set(sample.text.map(text_key)) & set(human.text.map(text_key)):
        raise ValueError("Muestra IA comparte texto con referencia humana")


def paired_video_bootstrap(gold, old, new, targets, *, draws=2000, seed=57):
    """Paired cluster bootstrap of fixed predictions; no refitting or test access."""
    validation = gold.loc[gold.split.eq("validation")]
    videos = sorted(set(validation.post_id)); lookup = {value: i for i, value in enumerate(videos)}
    arrays = []
    for predictions in (old, new):
        confusion = np.zeros((len(videos), 5, 5))
        coverage = np.zeros((len(videos), 3, 2))
        pairs = {(row["sample_id"], row["target_id"]): row for row in predictions.to_dict("records")}
        for row in predictions.to_dict("records"):
            confusion[lookup[row["post_id"]], LABELS.index(row["label"]), LABELS.index(row["valence"])] += float(row["weight"])
        for row in validation.to_dict("records"):
            for item in json.loads(row["annotation_json"]):
                if item["valence"] not in LABELS[:3]:
                    continue
                prediction = pairs.get((row["sample_id"], item["target_id"]))
                accepted = bool(prediction and str(prediction["accepted"]).lower() in ("true", "1")
                    and str(prediction["context_windowed"]).lower() in ("false", "0"))
                block = targets.get(item["target_id"], {}).get("target_group", "unknown")
                indices = [0] + ([1] if block == "izquierda" else [2] if block == "derecha" else [])
                for index in indices:
                    coverage[lookup[row["post_id"]], index] += np.array([accepted, 1]) / float(row["sampling_probability"])
        arrays.append((confusion, coverage))
    def metrics(counts):
        values = []
        for confusion, coverage in arrays:
            matrix = np.tensordot(counts, confusion, axes=1)
            denominators = matrix.sum(axis=0) + matrix.sum(axis=1)
            f1 = np.divide(2 * np.diag(matrix), denominators, out=np.zeros(5), where=denominators > 0)[:3].mean()
            totals = np.tensordot(counts, coverage, axes=1)
            ratios = np.divide(totals[:, 0], totals[:, 1], out=np.full(3, np.nan), where=totals[:, 1] > 0)
            values.append(np.r_[f1, ratios])
        return values[1] - values[0]
    point = metrics(np.ones(len(videos)))
    rng = np.random.default_rng(seed)
    samples = np.array([metrics(rng.multinomial(len(videos), np.full(len(videos), 1 / len(videos)))) for _ in range(draws)])
    intervals = {}
    for index, name in enumerate(("macro_f1_weighted", "global_coverage", "left_coverage", "right_coverage")):
        valid = samples[:, index][np.isfinite(samples[:, index])]
        intervals[name] = {"difference": float(point[index]), "ci95": np.quantile(valid, [.025, .975]).tolist() if len(valid) else None,
                           "valid_draws": len(valid)}
    return {"method": "paired_video_cluster_percentile_bootstrap_fixed_predictions", "draws": draws, "seed": seed,
            "videos": len(videos), "limitation": "Validación reutilizada; IC condicionales a modelos y calibración fijos. No incluyen selección ni incertidumbre de etiquetas.",
            "differences": intervals}


def tune(settings, run, root, gold, pairs, plan, source):
    from .development import fit_seed, finish_model, verify_accumulation
    if (root / "finalists").exists():
        raise ValueError("No repetir la ronda IA ya iniciada")
    verify_accumulation()
    training = pairs.loc[pairs.split.eq("train")].copy(); validation = pairs.loc[pairs.split.eq("validation")].copy()
    spec = plan["models"][0]; path = root / "finalists" / spec["id"]
    trial = {"id": spec["id"], "learning_rate": 1e-5, "objective": "ai_augmented"}
    revisions, logits = [], []
    for seed in plan["final_seeds"]:
        revision, values = fit_seed(settings, training, validation, path / "model", spec, trial, plan, seed)
        revisions.append(revision); logits.append(values)
        atomic_json(root / "progress.json", {"fits_completed": len(revisions), "maximum_fits": 3, "final_test_evaluated": False})
    report = finish_model(settings, run, source, path, spec, trial, validation, revisions, logits, gold_override=gold)
    item = {"id": spec["id"], "report": report, "model_path": str(path.relative_to(root) / "model"), "trial_id": trial["id"]}
    atomic_json(root / "selection.json", {"created_at": stamp(), "selected": {k: v for k, v in item.items() if k != "report"} if report["ready_for_reserved_test"] else None,
        "status": "ready_for_reserved_test" if report["ready_for_reserved_test"] else "development_requirements_not_met",
        "fits_completed": 3, "maximum_fits": 3, "finalists": [item], "final_test_evaluated": False})
    render(root, settings)


def render(root, settings=None):
    from .common import config
    settings = settings or config("config/targeted_v2.toml")
    from .development import render_comparison
    render_comparison(root)
    source = json.loads((root / "source.json").read_text())
    plan = json.loads((root / "plan.json").read_text())
    name = plan["models"][0]["id"]
    gold = read_csv(root / "human_development.csv")
    gold["items"] = gold.annotation_json.map(json.loads)
    gold["weight"] = 1 / gold.sampling_probability.astype(float)
    registry = load_registry(settings["registry"]); matcher = Matcher(registry)
    targets = {item["target_id"]: item for item in registry["targets"]}
    comparisons, coverage = {}, []
    for model, path in (("beto_previous", root / "baseline/validation_predictions.csv"), (name, root / "finalists" / name / "validation_predictions.csv")):
        parts, _, metrics = validation_diagnostics(gold, path, targets, matcher)
        comparisons[model] = {key: value for key, value in metrics.items() if key != "performance_slices"}
        coverage.extend({"model": model, **row} for row in parts)
    old, new = comparisons["beto_previous"], comparisons[name]
    def group_coverage(model, group):
        return next(row["weighted_share"] for row in coverage if row["model"] == model and row["dimension"] == "target_group" and row["value"] == group and row["status"] == "accepted")
    checks = {"macro_f1_not_decreased": new["macro_f1_weighted"] >= old["macro_f1_weighted"],
        "global_coverage_increased": new["coverage_all_evaluable_targets"] > old["coverage_all_evaluable_targets"],
        "left_coverage_increased": group_coverage(name, "izquierda") > group_coverage("beto_previous", "izquierda"),
        "right_coverage_not_decreased": group_coverage(name, "derecha") >= group_coverage("beto_previous", "derecha")}
    report = json.loads((root / "finalists" / name / "validation_report.json").read_text())
    checks["accepted_precisions_preserved"] = report["checks"]["positive_precision"] and report["checks"]["negative_precision"]
    bootstrap = paired_video_bootstrap(gold, read_csv(root / "baseline/validation_predictions.csv"),
        read_csv(root / "finalists" / name / "validation_predictions.csv"), targets)
    atomic_json(root / "report/augmentation_comparison.json", {"models": comparisons, "partial_improvement_checks": checks, "paired_bootstrap": bootstrap,
        "partial_development_improvement": all(checks.values()), "final_test_evaluated": False})
    pd.DataFrame(coverage).to_csv(root / "report/coverage_by_group.csv", index=False)
    with (root / "report/comparison.md").open("a") as handle:
        handle.write("\n## Ampliación IA\n\nEtiquetas IA exclusivamente auxiliares de entrenamiento; validación humana reutilizada/asistida.\n\n")
        handle.write(f"Comentarios IA: {source['counts']['ai_comments']}; pares entrenables: {source['counts']['ai_pairs']}; inciertos excluidos: {source['counts']['excluded_uncertain_pairs']}.\n\n")
        handle.write("| Bloque | Cobertura anterior | Cobertura ampliada |\n|---|---:|---:|\n")
        for group in ("izquierda", "derecha"):
            handle.write(f"| {group} | {group_coverage('beto_previous', group):.2%} | {group_coverage(name, group):.2%} |\n")
        handle.write(f"\nMejora parcial según criterios congelados: {'sí' if all(checks.values()) else 'no'}. No equivale a prueba final superada ni valida AP individual.\n")
        handle.write("\nDiferencias (ampliado − anterior), IC95% bootstrap pareado por video, modelos/calibración fijos:\n\n")
        for metric, values in bootstrap["differences"].items():
            handle.write(f"- {metric}: {values['difference']:.4f}; IC95% {values['ci95']}.\n")
        handle.write("\n" + bootstrap["limitation"] + "\n")
