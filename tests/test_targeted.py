from __future__ import annotations

import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pandas as pd

from polarization_pipeline.targeted.annotations import cohen_kappa, export_annotations, import_annotations, parse_review, split_for_video, stratified_sample, training_pairs
from polarization_pipeline.targeted.collection import BudgetedAPI, CollectionPaused, collect_video, select_panel
from polarization_pipeline.targeted.common import atomic_json, config, in_window, sha256, stages
from polarization_pipeline.targeted.corpus import build_corpus
from polarization_pipeline.targeted.learning import calibrate, classification_metrics, evaluation_report, probabilities, encoding, complete_context
from polarization_pipeline.targeted.metrics import analyze_targeted, collapse_events, clustered_inference, holm, partition_videos, summaries, user_scores
from polarization_pipeline.targeted.registry import Matcher, load_registry, registry_fingerprint


PERIODS = {"antes": ["2026-01-01T00:00:00Z", "2026-03-31T23:59:59Z"],
           "durante": ["2026-04-01T00:00:00Z", "2026-04-30T23:59:59Z"],
           "despues": ["2026-05-01T00:00:00Z", "2026-06-30T23:59:59Z"]}


def registry():
    return {"schema_version": 1, "version": "test", "status": "reviewed", "targets": [
        {"target_id": "a", "name": "Actor Á", "aliases": ["Actor Á"], "target_group": "izquierda", "entity_type": "political_actor", "valid_from": "2026-01-01", "valid_to": "2026-06-30", "sources": ["https://example.org/a"]},
        {"target_id": "b", "name": "Actor B", "aliases": ["Actor B"], "target_group": "derecha", "entity_type": "political_actor", "valid_from": "2026-01-01", "valid_to": "2026-06-30", "sources": ["https://example.org/b"]},
    ]}


def video(fold, number):
    for i in range(number * 100, number * 100 + 100):
        candidate = f"video_{i}"
        if partition_videos(pd.DataFrame({"post_id": [candidate]}), 42).iloc[0] == fold:
            return candidate
    raise AssertionError("No suitable video")


def settings():
    return {"seed": 42, "minimum_positive_videos": 2, "affinity_positive_share": 2 / 3,
            "evaluation_min_interactions": 3, "evaluation_min_videos": 2,
            "bootstrap_iterations": 20, "permutations": 20}


def events():
    rows = []
    for uid, group in (("l", "izquierda"), ("r", "derecha")):
        opposite = "derecha" if group == "izquierda" else "izquierda"
        for i in (1, 2):
            rows.append({"comment_id": f"{uid}_a{i}", "post_id": video("A", i), "user_id": uid, "target_group": group, "valence": "positive"})
        rows.extend([
            {"comment_id": f"{uid}_b1", "post_id": video("B", 3), "user_id": uid, "target_group": group, "valence": "positive"},
            {"comment_id": f"{uid}_b2", "post_id": video("B", 3), "user_id": uid, "target_group": opposite, "valence": "negative"},
            {"comment_id": f"{uid}_b3", "post_id": video("B", 4), "user_id": uid, "target_group": opposite, "valence": "neutral"},
        ])
    result = pd.DataFrame(rows)
    result["channel_id"] = result.post_id.map(lambda value: "c" + value.split("_")[1])
    result["party"] = "neutral"  # A neutral source may contain evaluations of political actors.
    result["comment_published_at"] = "2026-04-15T00:00:00Z"
    result["corpus"] = "main"
    return result


class RegistryTests(unittest.TestCase):
    def test_explicit_alias_offsets_and_date(self):
        matcher = Matcher(registry())
        text = "Me gusta Actor A, pero no Actor B"
        found = matcher.find(text, "2026-04-01")
        self.assertEqual([item["target_id"] for item in found], ["a", "b"])
        self.assertEqual(text[found[0]["mention_start"]:found[0]["mention_end"]], "Actor A")
        self.assertEqual(matcher.find(text, "2025-04-01"), [])

    def test_words_do_not_match_substrings(self):
        self.assertEqual(Matcher(registry()).find("Actor ABC"), [])

    def test_missing_political_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.json"
            value = registry()
            value["targets"][0]["sources"] = []
            atomic_json(path, value)
            with self.assertRaisesRegex(ValueError, "fuente"):
                load_registry(path)

    def test_review_status_does_not_invalidate_target_definitions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.json"
            value = registry()
            atomic_json(path, value)
            old = registry_fingerprint(path)
            value["status"] = "seed_requires_reviewer_audit"
            atomic_json(path, value)
            self.assertEqual(old, registry_fingerprint(path))
            with self.assertRaisesRegex(ValueError, "reviewed"):
                load_registry(path, frozen=True)


class CorpusTests(unittest.TestCase):
    def test_comment_time_not_video_stage(self):
        dates = pd.Series(["2026-04-12T00:00:00Z", "2026-07-01T00:00:00Z", "invalid"])
        self.assertEqual(stages(dates, PERIODS).tolist(), ["durante", "", ""])
        self.assertEqual(in_window(dates, PERIODS).tolist(), [True, False, False])

    def test_requires_verified_video_and_preserves_legacy_source(self):
        from polarization_pipeline.targeted.common import sha256
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, raw = root / "run", root / "raw"
            run.mkdir()
            raw.mkdir()
            source = root / "source.csv"
            pd.DataFrame([{"comment_id": "c", "post_id": "v", "user_id": "u", "text": "texto", "party": "izquierda", "channel": "canal", "published_at": "2026-04-12T00:00:00Z", "stage": "antes"}]).to_csv(source, index=False)
            atomic_json(raw / "izquierda.json", {"videos": [{"video_id": "v", "publicado": "2026-02-01T00:00:00Z", "canal_id": "cid"}]})
            atomic_json(run / "manifest.json", {"input_csv": str(source), "input_sha256": sha256(source)})
            setting = {"_root": root, "source": {"paths": {"raw": str(raw)}, "youtube": {"periods": PERIODS}}}
            self.assertEqual(build_corpus(setting, run)["rows_main_verified"], 0)
            pd.DataFrame([{"post_id": "v", "channel_id": "cid", "video_published_at": "2026-02-01T00:00:00Z", "video_status": "verified"}]).to_csv(run / "video_metadata.csv", index=False)
            self.assertEqual(build_corpus(setting, run)["rows_main_verified"], 1)
            frame = pd.read_csv(run / "corpus_main.csv")
            self.assertEqual(frame.comment_stage.iloc[0], "durante")
            self.assertEqual(frame.video_stage_legacy.iloc[0], "antes")
            self.assertEqual(frame.party.iloc[0], "izquierda")


class MetricTests(unittest.TestCase):
    def test_target_group_independent_of_neutral_source(self):
        result = user_scores(events(), settings()).set_index("user_id")
        self.assertEqual(result.loc["l", "ingroup"], "izquierda")
        self.assertEqual(result.loc["r", "ingroup"], "derecha")
        self.assertTrue(result.paired.all())
        self.assertAlmostEqual(result.loc["l", "gap"], 1.5)
        self.assertEqual(result.loc["l", "AP_target"], 2)
        self.assertAlmostEqual(result.loc["l", "spread"], np.sqrt(2 / 3))

    def test_outcome_does_not_define_affinity(self):
        frame = events()
        frame.loc[partition_videos(frame).eq("B"), "valence"] = "negative"
        self.assertEqual(user_scores(frame, settings()).ingroup.tolist(), user_scores(events(), settings()).ingroup.tolist())

    def test_no_outgroup_observation_is_not_neutrality(self):
        frame = events()
        frame = frame.loc[~(frame.user_id.eq("l") & partition_videos(frame).eq("B") & frame.target_group.eq("derecha"))]
        result = user_scores(frame, settings()).set_index("user_id")
        self.assertFalse(result.loc["l", "out_observed"])
        self.assertFalse(result.loc["l", "paired"])
        self.assertTrue(np.isnan(result.loc["l", "out_rate"]))

    def test_activity_scaling_changes_counts_but_not_rates(self):
        frame = events()
        duplicates = frame.copy()
        duplicates.comment_id += "copy"
        first = user_scores(frame, settings()).set_index("user_id")
        second = user_scores(pd.concat([frame, duplicates]), settings()).set_index("user_id")
        self.assertTrue(np.allclose(first.gap, second.gap))
        self.assertTrue(np.allclose(2 * first.AP_target, second.AP_target))
        self.assertTrue(np.allclose(np.sqrt(2) * first.spread, second.spread))

    def test_tie_is_undetermined(self):
        frame = events()
        extra = frame.loc[partition_videos(frame).eq("A")].copy()
        extra["target_group"] = extra.target_group.map({"izquierda": "derecha", "derecha": "izquierda"})
        extra.comment_id += "opposite"
        result = user_scores(pd.concat([frame, extra]), settings())
        self.assertTrue(result.ingroup.eq("Undetermined").all())
        self.assertTrue(result.gap.isna().all())

    def test_repeated_actor_and_contradictory_targets(self):
        frame = events().iloc[[0]].copy()
        frame["target_id"], frame["accepted"] = "actor", True
        prediction = pd.concat([frame, frame])
        self.assertEqual(len(collapse_events(prediction)), 1)
        opposite = frame.copy()
        opposite["target_id"], opposite["valence"] = "another_actor_same_block", "negative"
        self.assertEqual(collapse_events(pd.concat([prediction, opposite])).valence.iloc[0], "mixed")

    def test_abstentions_do_not_become_neutral(self):
        frame = events().iloc[[0]].copy()
        frame["target_id"], frame["accepted"] = "actor", False
        self.assertEqual(collapse_events(frame).valence.iloc[0], "abstained")

    def test_negative_opponent_under_own_source(self):
        frame = events()
        frame["party"] = "izquierda"
        self.assertEqual(user_scores(frame, settings()).set_index("user_id").loc["l", "AP_Out"], -1)

    def test_bootstrap_known_effect_and_no_effect(self):
        inference = clustered_inference(events(), settings()).set_index("contrast")
        self.assertAlmostEqual(inference.loc["gap", "estimate"], 1.5)
        frame = events()
        frame.loc[partition_videos(frame).eq("B"), "valence"] = "positive"
        self.assertAlmostEqual(summaries(user_scores(frame, settings()))["gap"], 0.0)

    def test_multiple_testing(self):
        self.assertTrue(np.allclose(holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06]))


class AnnotationTests(unittest.TestCase):
    def test_video_split_stable(self):
        self.assertEqual(split_for_video("same_video", 42), split_for_video("same_video", 42))

    def test_blank_form_cannot_train(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review.csv"
            sample = pd.DataFrame([{"sample_id": "s", "comment_id": "c", "text": "Actor A"}])
            sample.assign(annotation_json="", review_complete="").to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "incompleta"):
                parse_review(path, sample, {"a"})

    def test_explicit_empty_list_is_reviewed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review.csv"
            sample = pd.DataFrame([{"sample_id": "s", "comment_id": "c", "text": "Sin referencia política"}])
            sample.assign(annotation_json="[]", review_complete="true").to_csv(path, index=False)
            self.assertEqual(parse_review(path, sample, {"a"}), {"s": []})

    def test_insufficient_sample_fails_without_silent_fallback(self):
        frame = pd.DataFrame({"party": ["neutral"], "month": ["2026-01"], "enrichment": ["none"]})
        with self.assertRaisesRegex(ValueError, "insuficiente"):
            stratified_sample(frame, 2, 42)

    def test_weighted_sample_reproducible(self):
        frame = pd.DataFrame({"id": range(100), "party": ["neutral"] * 100, "month": ["2026-01"] * 100, "enrichment": ["candidate"] * 20 + ["none"] * 80})
        sample = stratified_sample(frame, 20, 42)
        self.assertEqual(sample.id.tolist(), stratified_sample(frame, 20, 42).id.tolist())
        self.assertEqual(len(sample), 20)
        self.assertTrue(sample.sampling_probability.between(0, 1).all())

    def test_kappa(self):
        self.assertEqual(cohen_kappa(["positive", "negative"], ["positive", "negative"]), 1)


class ModelTests(unittest.TestCase):
    def test_omitted_targets_fail_validation_even_with_perfect_conditional_f1(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.json"
            atomic_json(path, registry())
            rows, predicted = [], []
            for index, (target, text, label) in enumerate((("a", "Actor A", "positive"), ("b", "Actor B", "negative"), ("a", "Actor A", "neutral"), ("unregistered:missing", "Actor C", "negative"))):
                row = {"sample_id": str(index), "post_id": str(index), "text": text, "comment_published_at": "2026-04-01",
                       "sampling_probability": 1, "annotation_json": json.dumps([{"target_id": target, "valence": label}])}
                rows.append(row)
                if index < 3:
                    predicted.append({**row, "target_id": target, "target_group": "izquierda" if target == "a" else "derecha",
                                      "weight": 1, "label": label, "valence": label, "accepted": True, "sentimiento": "negative"})
            setting = {"registry": path, "seed": 42, "bootstrap_iterations": 20,
                       "quality": {"target_precision": 0.9, "target_recall": 0.8, "macro_f1": 0.75, "valence_precision": 0.85, "coverage": 0.6}}
            frame = pd.DataFrame(predicted)
            report = evaluation_report(setting, pd.DataFrame(rows), frame, frame)
            self.assertEqual(report["raw"]["macro_f1"], 1)
            self.assertAlmostEqual(report["target_recall"], 0.75)
            self.assertEqual(report["status"], "failed")
            self.assertFalse(report["checks"]["target_recall"])
            self.assertEqual(report["general_sentiment_baseline"]["pairs"], 3)

    def test_complete_context_is_not_cropped_or_normalized_away(self):
        class Tokenizer:
            def encode(self, text, **kwargs):
                return [ord(char) for char in text]
            def decode(self, values, **kwargs):
                return "".join(chr(value) for value in values)
            def num_special_tokens_to_add(self, **kwargs):
                return 4
            def __call__(self, targets, texts, **kwargs):
                return {"targets": targets, "texts": texts}
        tokenizer = Tokenizer()
        frame = pd.DataFrame([{"text": "Me gusta Actor A", "target_name": "Actor A", "mention_start": 9}])
        self.assertTrue(complete_context(tokenizer, frame, 40)[0])
        self.assertEqual(encoding(tokenizer, frame.to_dict("records"), 40)["texts"], frame.text.tolist())
        frame.loc[0, "text"] = "Texto largo " * 100 + "Actor A"
        self.assertFalse(complete_context(tokenizer, frame, 40)[0])

    def test_probabilities_and_confidence_are_not_emotion_intensity(self):
        values = probabilities(np.array([[1, 2, 3, 4, 5], [10, 20, 30, 40, 50]]))
        self.assertTrue(np.allclose(values.sum(axis=1), 1))
        self.assertTrue(np.all(values >= 0))

    def test_selective_classifier_cannot_pass_without_positive_predictions(self):
        report = classification_metrics(["positive", "negative"], ["neutral", "negative"])
        self.assertEqual(report["classes"]["positive"]["precision"], 0)

    def test_threshold_cannot_pass_on_one_confident_example(self):
        result = calibrate(np.array([[20, 0, 0, 0, 0]]), np.array(["positive"]), np.array([1.0]), 0.85)
        self.assertGreater(result["thresholds"]["positive"], 1)

    def test_disabled_valence_preserves_reserved_test_locally_and_remotely(self):
        from polarization_pipeline.targeted.learning import evaluate
        from polarization_pipeline.targeted.remote import prepare_job
        for disabled in ("positive", "negative"):
            with self.subTest(disabled=disabled), tempfile.TemporaryDirectory() as temp:
                run = Path(temp)
                (run / "annotations").mkdir()
                (run / "annotations/gold.csv").write_text("reserved labels must not be read")
                thresholds = {"positive": 0.65, "negative": 0.75, "neutral": 1.01}
                thresholds[disabled] = 1.01
                atomic_json(run / "model/calibration.json", {"precision_target": 0.85, "thresholds": thresholds})
                atomic_json(run / "model/training_manifest.json", {
                    "gold_sha256": sha256(run / "annotations/gold.csv"),
                    "checkpoint_hashes": {"calibration.json": sha256(run / "model/calibration.json")}})
                setting = {"quality": {"valence_precision": 0.85}}
                with patch("polarization_pipeline.targeted.learning._gpu") as gpu, \
                        patch("polarization_pipeline.targeted.learning.read_csv", side_effect=AssertionError("Reserved data read")):
                    with self.assertRaisesRegex(ValueError, "Calibración insuficiente.*" + disabled):
                        evaluate(setting, run)
                    gpu.assert_not_called()
                with self.assertRaisesRegex(ValueError, "Calibración insuficiente.*" + disabled):
                    prepare_job(setting, run, "evaluate")
                self.assertFalse((run / "model/test_opened.json").exists())
                self.assertFalse((run / "kaggle").exists())

    def test_test_calibration_checks_integrity_but_allows_neutral_abstention(self):
        from polarization_pipeline.targeted.learning import require_test_calibration
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            path = run / "model/calibration.json"
            calibration = {"precision_target": 0.85, "thresholds": {"positive": 0.65, "negative": 0.75, "neutral": 1.01}}
            atomic_json(path, calibration)
            atomic_json(run / "model/training_manifest.json", {"checkpoint_hashes": {"calibration.json": sha256(path)}})
            require_test_calibration({"quality": {"valence_precision": 0.85}}, run)
            calibration["thresholds"]["negative"] = 0.1
            atomic_json(path, calibration)
            with self.assertRaisesRegex(ValueError, "no coincide"):
                require_test_calibration({"quality": {"valence_precision": 0.85}}, run)

    def test_nonfinite_or_missing_calibration_cannot_enable_reserved_test(self):
        from polarization_pipeline.targeted.learning import require_test_calibration
        for threshold in (None, float("nan"), float("inf"), True):
            with self.subTest(threshold=threshold), tempfile.TemporaryDirectory() as temp:
                run = Path(temp)
                path = run / "model/calibration.json"
                path.parent.mkdir()
                path.write_text(json.dumps({"precision_target": 0.85, "thresholds": {"positive": 0.65, "negative": threshold}}))
                atomic_json(run / "model/training_manifest.json", {"checkpoint_hashes": {"calibration.json": sha256(path)}})
                with self.assertRaisesRegex(ValueError, "Calibración insuficiente"):
                    require_test_calibration({"quality": {"valence_precision": 0.85}}, run)


class CollectionTests(unittest.TestCase):
    def test_budget_is_persistent(self):
        class Resource:
            def list(self, **kwargs):
                return self
            def execute(self):
                return {"items": []}
        class API:
            def videos(self):
                return Resource()
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "usage.json"
            first = BudgetedAPI(API(), ledger, 1)
            first.call("videos", part="snippet")
            with self.assertRaises(CollectionPaused):
                BudgetedAPI(API(), ledger, 1).call("videos", part="snippet")

    def test_partial_embedded_replies_completed_and_resume_is_idempotent(self):
        def comment(cid, parent=""):
            return {"id": cid, "snippet": {"textOriginal": cid, "publishedAt": "2026-04-01T00:00:00Z", "parentId": parent}}
        class API:
            def __init__(self):
                self.calls = []
            def call(self, resource, **params):
                self.calls.append((resource, params))
                if resource == "commentThreads":
                    return {"items": [{"snippet": {"topLevelComment": comment("root"), "totalReplyCount": 2}, "replies": {"comments": [comment("r1", "root")]}}]}
                return {"items": [comment("r1", "root"), comment("r2", "root")]}
        with tempfile.TemporaryDirectory() as temp:
            api = API()
            path = Path(temp) / "video.json"
            state = collect_video(api, {"post_id": "v"}, path, PERIODS)
            self.assertEqual(state["status"], "complete")
            self.assertEqual(len(state["comments"]), 3)
            self.assertEqual(state["comments"]["r2"]["parent_id"], "root")
            self.assertEqual(api.calls[0][1]["order"], "time")
            collect_video(api, {"post_id": "v"}, path, PERIODS)
            self.assertEqual(len(api.calls), 2)

    def test_budget_interruption_preserves_page_checkpoint(self):
        class API:
            def call(self, resource, **params):
                raise CollectionPaused("pause")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "v.json"
            with self.assertRaises(CollectionPaused):
                collect_video(API(), {"post_id": "v"}, path, PERIODS)
            self.assertEqual(json.loads(path.read_text())["status"], "incomplete")


class WorkflowTests(unittest.TestCase):
    """Synthetic fixtures live only in temporary directories, never the real human study."""

    def human_fixture(self, root):
        run = root / "run"
        folder = run / "annotations"
        folder.mkdir(parents=True)
        path = root / "registry.json"
        atomic_json(path, registry())
        sample = pd.DataFrame([
            {"sample_id": "s1", "comment_id": "c1", "text": "Actor A", "pilot": "true", "post_id": "v1", "split": "train", "sampling_probability": "1", "comment_published_at": "2026-04-01"},
            {"sample_id": "s2", "comment_id": "c2", "text": "Actor B", "pilot": "true", "post_id": "v2", "split": "validation", "sampling_probability": "1", "comment_published_at": "2026-04-01"},
            {"sample_id": "s3", "comment_id": "c3", "text": "Sin objetivos", "pilot": "false", "post_id": "v3", "split": "test", "sampling_probability": "1", "comment_published_at": "2026-04-01"},
        ])
        sample.to_csv(folder / "sampling_manifest.csv", index=False)
        annotations = [json.dumps([{"target_id": "a", "valence": "positive", "mention_start": 0, "mention_end": 7}]),
                       json.dumps([{"target_id": "b", "valence": "negative", "mention_start": 0, "mention_end": 7}]), "[]"]
        for reviewer in (1, 2):
            sample[["sample_id", "comment_id", "text"]].assign(annotation_json=annotations, review_complete="true").to_csv(folder / f"reviewer_{reviewer}.csv", index=False)
        atomic_json(folder / "manifest.json", {"registry_sha256": registry_fingerprint(path), "sampling_sha256": sha256(folder / "sampling_manifest.csv")})
        return run, {"registry": path, "quality": {"kappa": 0.70}}

    def test_two_reviews_import_and_training_pairs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, setting = self.human_fixture(root)
            import_annotations(setting, run)
            self.assertEqual(json.loads((run / "annotations/manifest.json").read_text())["status"], "adjudicated")
            pairs = training_pairs(setting, run)
            self.assertEqual(set(pairs.label), {"positive", "negative"})
            self.assertEqual(len(pairs), 2)

    def test_pilot_allows_remaining_forms_to_be_blank(self):
        with tempfile.TemporaryDirectory() as temp:
            run, setting = self.human_fixture(Path(temp))
            for reviewer in (1, 2):
                path = run / "annotations" / f"reviewer_{reviewer}.csv"
                frame = pd.read_csv(path, keep_default_na=False, dtype=str)
                frame.loc[frame.sample_id.eq("s3"), ["annotation_json", "review_complete"]] = ""
                frame.to_csv(path, index=False)
            import_annotations(setting, run, pilot_only=True)
            self.assertTrue((run / "annotations/pilot_agreement.json").exists())
            self.assertFalse((run / "annotations/gold.csv").exists())
            with self.assertRaisesRegex(ValueError, "incompleta"):
                import_annotations(setting, run)

    def test_modified_gold_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            run, setting = self.human_fixture(Path(temp))
            import_annotations(setting, run)
            with (run / "annotations/gold.csv").open("a") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "cambiaron"):
                training_pairs(setting, run)

    def test_refresh_cannot_overwrite_any_human_work(self):
        with tempfile.TemporaryDirectory() as temp:
            run, setting = self.human_fixture(Path(temp))
            before = sha256(run / "annotations/reviewer_1.csv")
            with self.assertRaisesRegex(ValueError, "trabajo humano"):
                export_annotations(setting, run, refresh_unreviewed=True)
            self.assertEqual(sha256(run / "annotations/reviewer_1.csv"), before)

    def test_analysis_smoke_produces_artifacts_without_touching_context(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            (run / "model").mkdir(parents=True)
            frame = events()
            frame["target_id"] = frame.target_group
            frame["accepted"] = True
            frame["confidence"] = 0.95
            frame["context_windowed"] = False
            frame.to_csv(run / "predictions.csv", index=False)
            frame.drop_duplicates("comment_id").to_csv(run / "corpus_main.csv", index=False)
            atomic_json(run / "prediction_manifest.json", {"predictions_sha256": sha256(run / "predictions.csv"), "corpus_main_sha256": sha256(run / "corpus_main.csv")})
            atomic_json(run / "model/evaluation.json", {"status": "synthetic_smoke_fixture"})
            agents = root / "AGENTS.md"
            agents.write_text("unmodified test context")
            setting = {**settings(), "outputs": root / "outputs", "_root": root, "method_version": "test-only", "model_seeds": []}
            output = analyze_targeted(setting, run, smoke=True)
            self.assertEqual(json.loads((output / "manifest.json").read_text())["status"], "complete")
            for name in ("contrasts.csv", "gap_distribution.png", "participation_null.csv", "monthly_contrasts.csv"):
                self.assertTrue((output / name).exists())
            self.assertEqual(agents.read_text(), "unmodified test context")

    def test_unvalidated_model_cannot_produce_production_results(self):
        from polarization_pipeline.reporting import START_MARKER, END_MARKER
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            (run / "model").mkdir(parents=True)
            (root / "AGENTS.md").write_text(START_MARKER + "\nlegacy\n" + END_MARKER)
            atomic_json(run / "prediction_manifest.json", {})
            atomic_json(run / "model/evaluation.json", {"status": "failed"})
            with self.assertRaisesRegex(ValueError, "prueba humana"):
                analyze_targeted({**settings(), "_root": root}, run)

    def test_remote_smoke_preparation_is_private_and_source_only(self):
        import tarfile
        from polarization_pipeline.targeted.remote import prepare_job
        setting = config()
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"
            run.mkdir()
            stage = prepare_job(setting, run, "smoke")
            meta = json.loads((stage / "kernel/kernel-metadata.json").read_text())
            self.assertTrue(meta["is_private"])
            self.assertNotEqual(meta["id"], setting["source"]["kaggle"]["kernel_id"])
            with tarfile.open(stage / "dataset/targeted_payload.tar.gz") as archive:
                names = archive.getnames()
                self.assertFalse(any(".env" in name or "corpus_main" in name for name in names))
            code = (stage / "kernel/kernel.py").read_text()
            compile(code, "kernel.py", "exec")
            job = json.loads((stage / "job_manifest.json").read_text())
            self.assertIn(job["payload_manifest_sha256"], code)

    def test_archive_traversal_rejected(self):
        import io
        import tarfile
        from polarization_pipeline.targeted.remote import import_job
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = root / "unsafe.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                member = tarfile.TarInfo("../../unsafe.txt")
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
            with self.assertRaisesRegex(ValueError, "inseguro"):
                import_job({}, root, archive_path)

    def test_terminal_form_only_saves_confirmed_human_labels(self):
        from polarization_pipeline.targeted.review import annotate
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, setting = self.human_fixture(root)
            path = run / "annotations/reviewer_1.csv"
            pd.DataFrame([{"sample_id": "s", "comment_id": "c", "text": "Actor A", "parent_text": "", "post_title": "Título", "pilot": "true", "annotation_json": "", "review_complete": ""}]).to_csv(path, index=False)
            other_before = sha256(run / "annotations/reviewer_2.csv")
            with patch("builtins.input", side_effect=["a", "Actor A", "positive", "", "s"]), patch("builtins.print"):
                annotate(setting, run, 1, pilot_only=True)
            saved = pd.read_csv(path, dtype=str, keep_default_na=False)
            self.assertEqual(saved.review_complete.iloc[0], "true")
            self.assertEqual(json.loads(saved.annotation_json.iloc[0])[0]["mention_start"], 0)
            self.assertEqual(sha256(run / "annotations/reviewer_2.csv"), other_before)

    def test_expanded_kaggle_input_has_verifiable_manifest(self):
        import tarfile
        from polarization_pipeline.targeted.remote import prepare_job
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stage = prepare_job(config(), root, "smoke")
            destination = root / "expanded"
            destination.mkdir()
            with tarfile.open(stage / "dataset/targeted_payload.tar.gz") as archive:
                archive.extractall(destination, filter="data")
            job = json.loads((stage / "job_manifest.json").read_text())
            self.assertEqual(sha256(destination / "payload_manifest.json"), job["payload_manifest_sha256"])
            files = json.loads((destination / "payload_manifest.json").read_text())
            self.assertTrue(all(sha256(destination / name) == digest for name, digest in files.items()))

    def test_training_upload_withholds_blind_test_labels(self):
        import tarfile
        from polarization_pipeline.targeted.remote import prepare_job
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, setting = self.human_fixture(root)
            import_annotations(setting, run)
            pd.DataFrame({"comment_id": ["c1", "c2", "c3"]}).to_csv(run / "corpus_main.csv", index=False)
            remote_settings = config()
            remote_settings["registry"] = setting["registry"]
            stage = prepare_job(remote_settings, run, "train")
            with tarfile.open(stage / "dataset/targeted_payload.tar.gz") as archive:
                gold_file = archive.extractfile("run/annotations/gold.csv")
                gold = pd.read_csv(gold_file, dtype=str)
                self.assertFalse(gold.split.eq("test").any())
                self.assertNotIn("s3", set(gold.sample_id))
                pairs = pd.read_csv(archive.extractfile("run/training_pairs.csv"), dtype=str)
                self.assertFalse(pairs.split.eq("test").any())
                manifest = json.load(archive.extractfile("run/annotations/manifest.json"))
                self.assertEqual(manifest["study_gold_sha256"], sha256(run / "annotations/gold.csv"))

    def test_balancing_evaluation_does_not_reassign_affinity(self):
        original = user_scores(events(), settings())
        variant = user_scores(events(), settings(), balance_unit="channel_id")
        self.assertEqual(original.ingroup.tolist(), variant.ingroup.tolist())
        self.assertTrue(variant.paired.all())

    def test_legacy_refresh_keeps_independent_study_sections(self):
        from polarization_pipeline.reporting import START_MARKER, END_MARKER, update_study_section, update_results_section
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            agents = root / "AGENTS.md"
            agents.write_text(START_MARKER + "\nold baseline\n" + END_MARKER)
            update_study_section(agents, "#### Participación entre fuentes (targeted-v1)", "#### Participación entre fuentes (targeted-v1)\nactivity evidence")
            update_study_section(agents, "#### Resultados dirigidos (targeted-v1)", "#### Resultados dirigidos (targeted-v1)\ntarget evidence")
            with patch("polarization_pipeline.reporting._render_comparison", return_value="new baseline"):
                update_results_section(agents, root, root / "unused.csv")
            text = agents.read_text()
            self.assertIn("new baseline", text)
            self.assertIn("activity evidence", text)
            self.assertIn("target evidence", text)
            self.assertEqual(text.count(START_MARKER), 1)

    def test_targeted_context_retains_baseline_and_replaces_own_section(self):
        from polarization_pipeline.reporting import START_MARKER, END_MARKER
        from polarization_pipeline.targeted.metrics import _update_context
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            agents = root / "AGENTS.md"
            agents.write_text("prefix\n" + START_MARKER + "\nlegacy baseline\n" + END_MARKER + "\nsuffix")
            score = user_scores(events(), settings())
            contrasts = pd.DataFrame([{"contrast": "gap", "estimate": 1.5, "ci_low": 1.0, "ci_high": 2.0, "p_holm": 0.03}])
            setting = {**settings(), "_root": root}
            output = root / "outputs/run"
            _update_context(setting, output, score, contrasts)
            _update_context(setting, output, score, contrasts)
            text = agents.read_text()
            self.assertIn("legacy baseline", text)
            self.assertEqual(text.count("#### Resultados dirigidos (targeted-v1)"), 1)
            self.assertEqual(text.count(START_MARKER), 1)
            self.assertTrue(text.endswith("suffix"))


if __name__ == "__main__":
    unittest.main()
