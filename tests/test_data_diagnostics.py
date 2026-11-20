from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.diagnostics import (EVENT_COLUMNS, diagnose_data, load_development,
    annotation_support, composition, opportunities, validation_diagnostics, weight_summary)
from polarization_pipeline.targeted.metrics import partition_videos
from polarization_pipeline.targeted.registry import Matcher, load_registry, registry_fingerprint


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


class DataDiagnosticTests(unittest.TestCase):
    def fixture(self, root):
        run = root / "study"
        run.mkdir()
        registry = {"schema_version": 1, "version": "synthetic", "status": "reviewed", "targets": [
            {"target_id": name, "name": name, "aliases": [alias], "target_group": group,
             "entity_type": "person", "sources": ["synthetic-test-source"],
             "valid_from": "2020-01-01", "valid_to": "2030-12-31"}
            for name, alias, group in [("left", "Izq", "izquierda"), ("right", "Der", "derecha")]]}
        atomic_json(root / "registry.json", registry)
        (root / "config.toml").write_text("synthetic=true\n")
        settings = {"_root": root, "_config_path": root / "config.toml", "source_config": root / "config.toml",
                    "registry": root / "registry.json", "outputs": root / "outputs", "seed": 42,
                    "minimum_positive_videos": 2, "evaluation_min_interactions": 3, "evaluation_min_videos": 2}
        video_folds = partition_videos(pd.DataFrame({"post_id": [f"v{i}" for i in range(30)]}), 42)
        a = [f"v{i}" for i in range(30) if video_folds.iloc[i] == "A"]
        b = [f"v{i}" for i in range(30) if video_folds.iloc[i] == "B"]
        corpus = [{"comment_id": f"c{i}", "user_id": "u", "post_id": video, "channel_id": "channel",
                   "party": "neutral", "comment_type": "top_level", "comment_published_at": "2026-02-01",
                   "corpus": "main", "text": text}
                  for i, (video, text) in enumerate([(a[0], "Izq"), (a[1], "Izq"), (b[0], "Izq Der"), (b[1], "Der"), ("reserved", "Izq")])]
        write_csv(run / "corpus_main.csv", corpus)
        gold = []
        for index, split, items in [(0, "train", [{"target_id": "left", "valence": "positive"}]),
                                    (2, "validation", [{"target_id": "left", "valence": "positive"}, {"target_id": "right", "valence": "negative"}]),
                                    (4, "test", None)]:
            gold.append({**corpus[index], "sample_id": f"s{index}", "split": split, "sampling_probability": ".5",
                         "annotation_json": json.dumps(items) if items is not None else "DO NOT DECODE RESERVED LABELS"})
        write_csv(run / "annotations/gold.csv", gold)
        gold_hash = sha256(run / "annotations/gold.csv")
        atomic_json(run / "annotations/manifest.json", {"gold_sha256": gold_hash,
            "registry_sha256": registry_fingerprint(settings["registry"]), "corpus_main_sha256": sha256(run / "corpus_main.csv")})
        (run / "model").mkdir()
        (run / "model/weights.bin").write_bytes(b"synthetic-weights")
        experiment = run / "experiments/example"
        atomic_json(experiment / "source.json", {"registry_sha256": sha256(settings["registry"]), "study_gold_sha256": gold_hash})
        predictions = []
        for name, label, group, accepted in [("left", "positive", "izquierda", "True"), ("right", "negative", "derecha", "False")]:
            predictions.append({**gold[1], "target_id": name, "target_group": group, "label": label,
                                "valence": label, "weight": 2, "accepted": accepted, "context_windowed": "False"})
        path = experiment / "finalists/example/validation_predictions.csv"
        write_csv(path, predictions)
        return settings, run, path

    def test_reserved_annotations_never_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, _ = self.fixture(Path(directory))
            gold, metadata = load_development(run)
            self.assertEqual(set(gold.split), {"train", "validation"})
            self.assertFalse(metadata["test_labels_decoded"])
            self.assertEqual(metadata["comments_by_split"]["test"], 1)

    def test_rejects_video_leakage_using_only_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, _ = self.fixture(Path(directory))
            path = run / "annotations/gold.csv"
            frame = read_csv(path)
            frame.loc[frame.split.eq("test"), "post_id"] = frame.loc[frame.split.eq("train"), "post_id"].iloc[0]
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "Videos compartidos"):
                load_development(run)

    def test_weight_effective_size_and_invalid_weights(self):
        self.assertAlmostEqual(weight_summary([1, 3])["effective_n_weights_only"], 1.6)
        for values in ([0], [-1], [float("nan")]):
            with self.assertRaisesRegex(ValueError, "Pesos"):
                weight_summary(values)

    def test_opportunity_deduplicates_block_mentions_and_handles_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, _ = self.fixture(Path(directory))
            matcher = Matcher(load_registry(settings["registry"]))
            events = []
            for row in read_csv(run / "corpus_main.csv").to_dict("records"):
                for match in matcher.find(row["text"], row["comment_published_at"]):
                    events.append({**{key: row.get(key, "") for key in EVENT_COLUMNS}, "target_group": match["target_group"]})
            frame = pd.DataFrame(events)
            users = Counter({"u": 5, "without_mentions": 8})
            table = opportunities(pd.concat([frame, frame]), users, settings, seed=42).set_index("user_id")
            self.assertTrue(table.loc["u", "potentially_paired"])
            self.assertEqual(table.loc["u", "political_mention_comments"], 5)
            self.assertFalse(table.loc["without_mentions", "potentially_paired"])
            empty = opportunities(pd.DataFrame(columns=EVENT_COLUMNS), users, settings, seed=42)
            self.assertEqual(int(empty.potentially_paired.sum()), 0)

    def test_coverage_reconciles_and_never_calls_missing_neutral(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, path = self.fixture(Path(directory))
            gold, _ = load_development(run)
            registry = load_registry(settings["registry"])
            rows, _, metrics = validation_diagnostics(gold, path, {t["target_id"]: t for t in registry["targets"]}, Matcher(registry))
            total = [row for row in rows if row["dimension"] == "all"]
            self.assertAlmostEqual(sum(row["weighted_share"] for row in total), 1)
            self.assertAlmostEqual(metrics["coverage_all_evaluable_targets"], .5)
            self.assertEqual(next(row["units"] for row in total if row["status"] == "low_confidence"), 1)

    def test_existing_audit_panel_is_profiled_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, _ = self.fixture(Path(directory))
            panel = read_csv(run / "corpus_main.csv").iloc[:2].copy()
            panel["corpus"] = "audit_panel"
            path = run / "corpus_panel.csv"
            panel.to_csv(path, index=False)
            summary, events, _, _ = composition(path, Matcher(load_registry(settings["registry"])), "panel")
            self.assertEqual(summary["rows"], 2)
            self.assertEqual(len(events), 2)

    def test_unregistered_human_targets_stay_unknown_and_count_as_omissions(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, path = self.fixture(Path(directory))
            gold, _ = load_development(run)
            index = gold.index[gold.split.eq("validation")][0]
            gold.at[index, "items"] = gold.at[index, "items"] + [{"target_id": "unregistered:Outside", "valence": "neutral"}]
            registry = load_registry(settings["registry"])
            targets = {t["target_id"]: t for t in registry["targets"]}
            support, _ = annotation_support(gold, targets)
            row = support.loc[support.value.eq("unregistered:Outside")].iloc[0]
            self.assertEqual(row.units, 1)
            rows, _, metrics = validation_diagnostics(gold, path, targets, Matcher(registry))
            unknown = [r for r in rows if r["dimension"] == "target_group" and r["value"] == "unknown" and r["status"] == "missed_target"][0]
            self.assertEqual(unknown["units"], 1)
            self.assertAlmostEqual(metrics["coverage_all_evaluable_targets"], 1/3)

    def test_two_events_still_required_if_one_assignment_video_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, _ = self.fixture(Path(directory))
            settings["minimum_positive_videos"] = 1
            first = read_csv(run / "corpus_main.csv").iloc[0].to_dict()
            first.update(target_group="izquierda", month="2026-02")
            one = pd.DataFrame([first])[EVENT_COLUMNS]
            users = Counter({"u": 2})
            self.assertFalse(opportunities(one, users, settings, seed=42).assignment_possible.iloc[0])
            two = pd.concat([one, one.assign(comment_id="another")], ignore_index=True)
            self.assertTrue(opportunities(two, users, settings, seed=42).assignment_possible.iloc[0])

    def test_rejects_reserved_prediction_ids_even_if_split_is_forged(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, path = self.fixture(Path(directory))
            frame = read_csv(path)
            frame.loc[0, "sample_id"] = "s4"
            frame.to_csv(path, index=False)
            gold, _ = load_development(run)
            registry = load_registry(settings["registry"])
            with self.assertRaisesRegex(ValueError, "fuera de validación"):
                validation_diagnostics(gold, path, {t["target_id"]: t for t in registry["targets"]}, Matcher(registry))

    def test_rejects_incomplete_prediction_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, path = self.fixture(Path(directory))
            read_csv(path).iloc[:1].to_csv(path, index=False)
            gold, _ = load_development(run)
            registry = load_registry(settings["registry"])
            with self.assertRaisesRegex(ValueError, "incompletas"):
                validation_diagnostics(gold, path, {t["target_id"]: t for t in registry["targets"]}, Matcher(registry))

    def test_end_to_end_no_network_preserves_inputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, _ = self.fixture(Path(directory))
            before = {str(p): sha256(p) for p in run.rglob("*") if p.is_file()}
            with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
                output = diagnose_data(settings, run, "audit1")
            self.assertEqual(before, {str(p): sha256(p) for p in run.rglob("*") if p.is_file()})
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertFalse(manifest["test_labels_decoded"])
            self.assertEqual(json.loads((output / "summary.json").read_text())["primary_opportunity"]["potentially_paired"], 1)
            self.assertFalse((run / "model/test_opened.json").exists())
            for name, digest in manifest["artifacts"].items():
                self.assertEqual(sha256(output / name), digest)
            with self.assertRaises(FileExistsError):
                diagnose_data(settings, run, "audit1")

    def test_changed_corpus_stops_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, run, _ = self.fixture(Path(directory))
            with (run / "corpus_main.csv").open("a") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "modificados"):
                diagnose_data(settings, run, "audit1")
            self.assertFalse(settings["outputs"].exists())


if __name__ == "__main__":
    unittest.main()
