"""Fixed human-only final refinement of verified AI-augmented checkpoints."""
from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import numpy as np

from .common import LABELS, atomic_json, read_csv, sha256, stamp
from .registry import Matcher, load_registry

PROTOCOL = "targeted-human-refinement-v1"
INPUTS = ("human_development.csv", "human_pairs.csv", "training_config.toml")
CONTROLS = {"beto_previous": "blend_0.00", "beto_ai_augmented": "blend_1.00", "blend_0.50": "blend_0.50"}


def validate_plan(plan):
    expected = {"schema_version": 1, "protocol": PROTOCOL, "parent_experiment_id": "development_ai_augmentation_v1",
        "comparison_experiment_id": "development_blend_20261116_v1", "maximum_fits": 3,
        "final_seeds": [42, 43, 44], "learning_rates": [2e-6], "objectives": ["class_balanced"],
        "maximum_epochs": 2, "fixed_epochs": True, "effective_batch_size": 16, "weight_decay": .01,
        "gradient_clip": 1., "calibration_folds": 5, "calibration_seed": 57,
        "models": [{"id": "beto_human_refined", "model": "dccuchile/bert-base-spanish-wwm-uncased",
            "revision": "d1c9c4565c9d6731e57ed7f027b802697bad861e", "maximum_tokens": 512, "physical_batch_size": 4}]}
    if any(plan.get(k) != v for k, v in expected.items()):
        raise ValueError("Conservar una receta, tres semillas y dos épocas fijas de refinamiento humano")


def validate_human_training(frame):
    if frame.empty or not frame.split.eq("train").all() or not frame.label_origin.eq("human_confirmed").all():
        raise ValueError("El refinamiento admite exclusivamente entrenamiento humano confirmado")
    if not set(frame.label) <= set(LABELS):
        raise ValueError("Etiquetas humanas inválidas")


def check_classifier_config(config):
    if config.get("model_type") != "bert" or config.get("target_representation", "pair_cls") not in (None, "pair_cls"):
        raise ValueError("Checkpoint inicial incompatible con BETO comentario–objetivo")
    if config.get("id2label") != {str(i): label for i, label in enumerate(LABELS)}:
        raise ValueError("No reiniciar ni permutar etiquetas del clasificador aprendido")
    if config.get("label2id") != {label: i for i, label in enumerate(LABELS)}:
        raise ValueError("Mapa inverso del clasificador incompatible")


def initialize_checkpoint(path):
    from transformers import AutoTokenizer
    from .targetaware import load_classifier
    check_classifier_config(json.loads((path / "config.json").read_text()))
    # Loading the saved classifier preserves its learned head and encoder.
    model = load_classifier(path, local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained(path, use_fast=False, local_files_only=True)
    return model, tokenizer


def verify_fixed_training():
    """Small real-torch GPU preflight: head reload, exactly two epochs, one validation pass."""
    import tempfile
    import pandas as pd
    from unittest.mock import patch
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizer
    from . import development
    from .learning import _gpu
    torch = _gpu()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp); checkpoint = base / "initial"; checkpoint.mkdir()
        vocab = checkpoint / "vocab.txt"
        vocab.write_text("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "actor", "apoyo", "rechazo", "mencion"]))
        tokenizer = BertTokenizer(vocab_file=str(vocab)); tokenizer.save_pretrained(checkpoint)
        config = BertConfig(vocab_size=9, hidden_size=16, intermediate_size=24, num_hidden_layers=1,
            num_attention_heads=2, max_position_embeddings=32, num_labels=5,
            id2label=dict(enumerate(LABELS)), label2id={v: i for i, v in enumerate(LABELS)})
        initial = BertForSequenceClassification(config); initial.save_pretrained(checkpoint)
        before = {p.name: sha256(p) for p in checkpoint.iterdir()}
        loaded, _ = initialize_checkpoint(checkpoint)
        if not torch.equal(initial.classifier.weight, loaded.classifier.weight):
            raise RuntimeError("El clasificador inicial fue reiniciado")
        del initial, loaded
        frame = pd.DataFrame([{"text": text, "target_name": "actor", "mention_start": 0, "mention_end": 5,
            "label": LABELS[i], "split": "train", "label_origin": "human_confirmed", "weight": 1.}
            for i, text in enumerate(["actor apoyo", "actor rechazo", "actor mencion"])])
        plan = {"fixed_epochs": True, "maximum_epochs": 2, "effective_batch_size": 3,
                "weight_decay": .01, "gradient_clip": 1.}
        spec = {"maximum_tokens": 32, "physical_batch_size": 1, "revision": "synthetic"}
        trial = {"objective": "class_balanced", "learning_rate": 2e-6}
        with patch.object(development, "predict_logits", wraps=development.predict_logits) as spy:
            revision, logits = development.fit_seed({}, frame, frame.assign(split="validation"), base / "model",
                spec, trial, plan, 42, initial_checkpoint=checkpoint)
        if spy.call_count != 1 or revision["best_epoch"] != 2 or len(revision["history"]) != 2 or logits.shape != (3, 5):
            raise RuntimeError("El refinamiento usó validación para elegir época o no completó dos épocas")
        if before != {p.name: sha256(p) for p in checkpoint.iterdir()}:
            raise RuntimeError("El checkpoint de entrada fue modificado")
        torch.cuda.empty_cache()
    print("HUMAN_REFINEMENT_PREFLIGHT_VERIFIED", flush=True)


def freeze(settings, run, experiment_id, training_config):
    from .development import experiment_directory
    root = experiment_directory(run, experiment_id)
    config_plan = tomllib.loads(Path(training_config).read_text()); validate_plan(config_plan)
    if root.exists():
        if not (root / "source.json").exists():
            raise ValueError("Preparación parcial conservada; no sobrescribir")
        if sha256(Path(training_config)) != json.loads((root / "plan.json").read_text())["training_config_sha256"]:
            raise ValueError("Configuración distinta del refinamiento congelado")
        verify(settings, run, root)
        return root
    if (run / "model/test_opened.json").exists():
        raise ValueError("La prueba final debe permanecer reservada")
    parent = experiment_directory(run, config_plan["parent_experiment_id"])
    comparison = experiment_directory(run, config_plan["comparison_experiment_id"])
    export = json.loads((parent / "export_tune.json").read_text())
    execution = json.loads((parent / "execution_report.json").read_text())
    compare_execution = json.loads((comparison / "execution_report.json").read_text())
    parent_source = json.loads((parent / "source.json").read_text())
    if (sha256(parent / "export_tune.json") != execution["export_sha256"]
        or sha256(parent / "source.json") != execution["source_sha256"]
        or execution["human_final_test_evaluated"] or compare_execution["final_test_evaluated"]
        or parent_source["quality"] != settings["quality"] or parent_source["registry_sha256"] != sha256(settings["registry"])):
        raise ValueError("Padre o comparación incompatible con el estudio")
    annotation_manifest = json.loads((run / "annotations/manifest.json").read_text())
    if sha256(run / "annotations/gold.csv") != annotation_manifest["gold_sha256"]:
        raise ValueError("Referencia humana original alterada")
    # Seal originals before creating this experiment; pending review data are opaque.
    from .diagnostics import protected_files
    protected = {k: v for k, v in protected_files(settings, run).items() if "/src/polarization_pipeline/" not in k}
    protected.update({str(p.resolve()): sha256(p) for p in (run / "cohorts").rglob("*") if p.is_file()})
    root.mkdir(parents=True)
    atomic_json(root / "protected_originals.json", protected)
    copied = []
    def copy(source, name, expected):
        if sha256(source) != expected:
            raise ValueError("Entrada padre alterada: " + name)
        destination = root / name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination); copied.append(name)
    for name in INPUTS[:2]:
        copy(parent / name, name, export["files"][name])
    shutil.copy2(training_config, root / "training_config.toml"); copied.append("training_config.toml")
    model_prefix = "finalists/beto_ai_augmented/model/"
    model_manifest = json.loads((parent / (model_prefix + "training_manifest.json")).read_text())
    if model_manifest["registry_sha256"] != sha256(settings["registry"]):
        raise ValueError("Checkpoint de otro registro")
    for seed in config_plan["final_seeds"]:
        for name, digest in model_manifest["checkpoint_hashes"].items():
            if name.startswith(str(seed) + "/"):
                if export["files"].get(model_prefix + name) != digest:
                    raise ValueError("Checkpoint ajeno al export padre")
                copy(parent / (model_prefix + name), "warmstart/" + name, digest)
        check_classifier_config(json.loads((root / "warmstart" / str(seed) / "config.json").read_text()))
    for name, control in CONTROLS.items():
        for filename in ("validation_predictions.csv", "cross_calibrated_predictions.csv", "reports.json"):
            relative = f"candidates/{control}/{filename}"
            copy(comparison / relative, f"controls/{name}/{filename}", compare_execution["artifacts"][relative])
    baseline = root / "baseline"; baseline.mkdir()
    shutil.copy2(root / "controls/blend_0.50/validation_predictions.csv", baseline / "validation_predictions.csv")
    atomic_json(baseline / "validation_report.json", json.loads((root / "controls/blend_0.50/reports.json").read_text())["full_development"])
    atomic_json(baseline / "manifest.json", {"origin": "frozen_blend_0.50", "parent": config_plan["comparison_experiment_id"]})
    copied.extend("baseline/" + p.name for p in baseline.iterdir())
    plan = {**config_plan, "experiment_id": experiment_id, "frozen_at": stamp(), "training_config_sha256": sha256(Path(training_config))}
    atomic_json(root / "plan.json", plan)
    source = {**{k: parent_source[k] for k in ("study_gold_sha256", "registry_sha256", "development_gold_sha256",
        "annotation_protocol", "annotation_limitation", "sampling_probability_scope", "quality")},
        "plan_sha256": sha256(root / "plan.json"), "input_hashes": {n: sha256(root / n) for n in copied},
        "lineage": {"parent_export_sha256": sha256(parent / "export_tune.json"),
            "parent_model_manifest_sha256": sha256(parent / (model_prefix + "training_manifest.json")),
            "comparison_execution_sha256": sha256(comparison / "execution_report.json")},
        "pending_reviews_used": False, "training_phase": "human_only_final_refinement_of_ai_augmented_checkpoint"}
    atomic_json(root / "source.json", source)
    verify(settings, run, root)
    return root


def verify(settings, run, root):
    source = json.loads((root / "source.json").read_text()); plan = json.loads((root / "plan.json").read_text()); validate_plan(plan)
    if (source["plan_sha256"] != sha256(root / "plan.json") or source["registry_sha256"] != sha256(settings["registry"])
        or source["quality"] != settings["quality"] or (run / "model/test_opened.json").exists()):
        raise ValueError("Refinamiento alterado o prueba abierta")
    for name, digest in source["input_hashes"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path) != digest:
            raise ValueError("Entrada de refinamiento alterada: " + name)
    gold = read_csv(root / "human_development.csv"); pairs = read_csv(root / "human_pairs.csv")
    if not gold.split.isin(["train", "validation"]).all() or not pairs.split.isin(["train", "validation"]).all():
        raise ValueError("Prueba final fuera del paquete de refinamiento")
    if not pairs.label_origin.eq("human_confirmed").all():
        raise ValueError("No incluir nuevas etiquetas IA o revisiones pendientes")
    if gold.groupby("post_id").split.nunique().gt(1).any() or gold.sample_id.duplicated().any():
        raise ValueError("Desarrollo duplicado o videos compartidos")
    from .ai_augmentation import human_pairs
    expected = human_pairs(gold, Matcher(load_registry(settings["registry"], frozen=True)))
    # Ignore origin column order/dtypes; require exactly regenerated human pairs.
    key = ["sample_id", "target_id"]
    for col in (*key, "label", "text", "post_id", "split", "target_group", "mention_start", "mention_end", "weight"):
        left = pairs.set_index(key).sort_index(); right = expected.set_index(key).sort_index()
        if not left.index.equals(right.index) or (col not in key and not left[col].astype(str).equals(right[col].astype(str))):
            if col == "weight" and left.index.equals(right.index) and np.allclose(left[col].astype(float), right[col].astype(float), rtol=1e-12):
                continue
            raise ValueError("Pares no corresponden a referencia humana: " + col)
    validate_human_training(pairs.loc[pairs.split.eq("train")])
    return gold, pairs


def tune(settings, run, root, gold, pairs, plan, source):
    from .development import fit_seed, finish_model, verify_accumulation
    if (root / "finalists").exists():
        raise ValueError("No repetir refinamiento iniciado")
    verify_accumulation()
    verify_fixed_training()
    training = pairs.loc[pairs.split.eq("train")].copy(); validation = pairs.loc[pairs.split.eq("validation")].copy()
    spec = plan["models"][0]; path = root / "finalists" / spec["id"]
    trial = {"id": spec["id"], "learning_rate": 2e-6, "objective": "class_balanced"}
    revisions, logits = [], []
    for seed in plan["final_seeds"]:
        revision, values = fit_seed(settings, training, validation, path / "model", spec, trial, plan, seed,
                                   initial_checkpoint=root / "warmstart" / str(seed))
        revision["initial_checkpoint_hashes"] = {n: d for n, d in source["input_hashes"].items() if n.startswith(f"warmstart/{seed}/")}
        revision["initialization"] = "ai_augmented_checkpoint_same_seed"
        revisions.append(revision); logits.append(values)
        atomic_json(root / "progress.json", {"fits_completed": len(revisions), "maximum_fits": 3, "final_test_evaluated": False})
    finish_model(settings, run, source, path, spec, trial, validation, revisions, logits, gold_override=gold)
    render(settings, root, gold)


def render(settings, root, gold):
    from .blending import PROB, aligned, cross_calibrate, development_report
    from .learning import probabilities
    from .ai_augmentation import paired_video_bootstrap
    path = root / "finalists/beto_human_refined"
    validation = gold.loc[gold.split.eq("validation")].copy()
    full = read_csv(path / "validation_predictions.csv")
    mean = np.mean([probabilities(np.load(path / f"model/validation_logits_{seed}.npy", allow_pickle=False)) for seed in (42, 43, 44)], axis=0)
    valid = full.context_windowed.astype(str).str.lower().isin(["false", "0"]).to_numpy()
    cross, folds = cross_calibrate(full, mean, valid, precision=settings["quality"]["valence_precision"])
    cross.to_csv(path / "cross_calibrated_predictions.csv", index=False)
    atomic_json(path / "calibration_folds.json", folds)
    reports = {"full_development": development_report(settings, validation, full),
               "cross_calibrated": development_report(settings, validation, cross)}
    atomic_json(path / "reports.json", reports)
    old = read_csv(root / "controls/blend_0.50/validation_predictions.csv")
    old_cross = read_csv(root / "controls/blend_0.50/cross_calibrated_predictions.csv")
    aligned(old, full); aligned(old_cross, cross)
    old_reports = json.loads((root / "controls/blend_0.50/reports.json").read_text())
    full_report = reports["full_development"]; cross_report = reports["cross_calibrated"]
    partial_checks = {"macro_f1_increased": full_report["raw"]["macro_f1"] > old_reports["full_development"]["raw"]["macro_f1"],
        "full_coverage_preserved": full_report["coverage"] >= old_reports["full_development"]["coverage"],
        "cross_coverage_preserved": cross_report["coverage"] >= old_reports["cross_calibrated"]["coverage"],
        "cross_positive_precision": cross_report["checks"]["positive_precision"], "cross_negative_precision": cross_report["checks"]["negative_precision"]}
    eligible = full_report["development_checks_passed"] and cross_report["development_checks_passed"]
    atomic_json(root / "selection.json", {"selected": "beto_human_refined" if eligible else None, "fits_completed": 3,
        "maximum_fits": 3, "partial_improvement_checks": partial_checks, "partial_development_improvement": all(partial_checks.values()),
        "final_test_evaluated": False, "production_enabled": False, "pending_reviews_used": False,
        "scope": "Validación reutilizada/asistida; calibración por video no elimina selección previa de los checkpoints padres."})
    targets = {t["target_id"]: t for t in load_registry(settings["registry"])["targets"]}
    atomic_json(root / "paired_bootstrap.json", paired_video_bootstrap(validation, old_cross, cross, targets))
    from .diagnostics import validation_diagnostics
    validation["items"] = validation.annotation_json.map(json.loads); validation["weight"] = 1 / validation.sampling_probability.astype(float)
    matcher = Matcher(load_registry(settings["registry"]))
    for kind in ("validation", "cross_calibrated"):
        slices, _, metrics = validation_diagnostics(validation, path / f"{kind}_predictions.csv", targets, matcher)
        import pandas as pd
        pd.DataFrame(slices).to_csv(path / f"{kind}_coverage_by_group.csv", index=False)
        atomic_json(path / f"{kind}_slices.json", metrics)
    lines = ["# Refinamiento humano final: desarrollo", "", "Tres semillas, dos épocas fijas, tasa 2e-6; sin revisión pendiente usada.",
        "Inicialización con checkpoints ampliados IA; solo la fase final usa exclusivamente referencia humana.", "",
        "| Modelo | F1 ponderado | Cobertura completa | Cobertura separada | P+ separada | P− separada |",
        "|---|---:|---:|---:|---:|---:|"]
    comparisons = [(n, json.loads((root / "controls" / n / "reports.json").read_text())) for n in CONTROLS] + [("beto_human_refined", reports)]
    for name, r in comparisons:
        f, c = r["full_development"], r["cross_calibrated"]
        lines.append(f"| {name} | {f['raw']['macro_f1']:.4f} | {f['coverage']:.2%} | {c['coverage']:.2%} | {c['accepted']['classes']['positive']['precision']:.2%} | {c['accepted']['classes']['negative']['precision']:.2%} |")
    lines += ["", f"Mejora parcial: {all(partial_checks.values())}; elegible en desarrollo: {eligible}.",
        "Validación reutilizada/asistida. Sin prueba final, AP nueva ni inferencia de producción. IC condicionales a modelos/calibración/folds fijos y sin selección ni incertidumbre de etiquetas.", ""]
    (root / "comparison.md").write_text("\n".join(lines))
