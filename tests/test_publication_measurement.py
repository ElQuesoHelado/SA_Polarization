"""Measurement can close from complete human histories without a classifier."""
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import test_publication as fixtures
from polarization_pipeline.targeted.assisted import annotation_digest
from polarization_pipeline.targeted.common import read_csv, sha256
from polarization_pipeline.targeted.metrics import partition_videos
from polarization_pipeline.targeted.publication import analysis, annotations
from polarization_pipeline.targeted.publication.measurement import (
    preflight, precision_assessment, validate_histories, coverage_tables)


class MeasurementTests(unittest.TestCase):
    def complete_synthetic_batch(self, study, reg, name="cohort_0001", outcome=None, empty=False):
        # These confirmations exist only in temporary synthetic fixtures.
        batch = fixtures.PublicationTests().proposals(study, name, reg)
        sample = read_csv(study / "annotations" / name / "sample.csv").set_index("sample_id")
        form = read_csv(study / "annotations" / name / "human_review.csv")
        proposals = {r["sample_id"]: r["annotations"] for r in batch["proposals"]}
        for index, row in form.iterrows():
            original = proposals[row.sample_id]
            items = json.loads(json.dumps(original))
            if empty:
                items = []
            elif outcome is not None and partition_videos(sample.loc[[row.sample_id]]).iloc[0] == "B":
                for item in items:
                    if outcome == "null":
                        item["valence"] = "neutral"
                    elif outcome == "negative":
                        item["valence"] = {"positive":"negative", "negative":"positive", "neutral":"neutral"}[item["valence"]]
            form.loc[index, ["annotation_json", "review_complete", "reviewer_id", "reviewed_at", "decision", "proposal_sha256"]] = [
                json.dumps(items), "true", "synthetic-human", "2026-11-18T10:00:00Z",
                "accepted" if items == original else "modified", annotation_digest(original)]
        form.to_csv(study / "annotations" / name / "human_review.csv", index=False)

    def test_preflight_waiting_snapshot_is_read_only_without_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = fixtures.PublicationTests().fixture(Path(tmp))
            before = {str(p):sha256(p) for p in Path(tmp).rglob("*") if p.is_file()}
            result = preflight(setting, plan, study, reg)
            self.assertEqual(result["status"], "waiting_snapshot")
            self.assertFalse(result["model_readiness_required"])
            self.assertEqual(before, {str(p):sha256(p) for p in Path(tmp).rglob("*") if p.is_file()})

    def test_preflight_requires_human_then_ready_despite_invalid_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = fixtures.PublicationTests().freeze_fixture(Path(tmp))
            self.assertEqual(preflight(setting, plan, study, reg)["status"], "waiting_cohort")
            annotations.next_batch(setting, plan, study, reg)
            result = preflight(setting, plan, study, reg)
            self.assertEqual(result["status"], "waiting_human_review")
            self.assertEqual(result["pending_comments"], 5)
            self.complete_synthetic_batch(study, reg)
            (study / "training").mkdir(); (study / "training/manifest.json").write_text("invalid model manifest")
            before = {str(p):sha256(p) for p in Path(tmp).rglob("*") if p.is_file()}
            result = preflight(setting, plan, study, reg)
            self.assertTrue(result["ready_for_analysis"])
            self.assertEqual(result["comparable_users"], 1)
            self.assertEqual(result["precision_status"], "not_assessed_before_analysis")
            self.assertFalse((study / "annotations/benchmark").exists())
            self.assertEqual(before, {str(p):sha256(p) for p in Path(tmp).rglob("*") if p.is_file()})

    def test_more_users_or_exhaustion_never_depend_on_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = fixtures.PublicationTests().freeze_fixture(Path(tmp))
            plan = {**plan, "comparable_users":2}
            annotations.next_batch(setting, plan, study, reg)
            self.complete_synthetic_batch(study, reg, empty=True)
            result = preflight(setting, plan, study, reg)
            self.assertEqual(result["status"], "waiting_comparable_users")
            self.assertEqual(result["comparable_users"], 0)
            annotations.next_batch(setting, plan, study, reg, stage="final")
            self.complete_synthetic_batch(study, reg, "cohort_0002", empty=True)
            result = preflight(setting, plan, study, reg)
            self.assertTrue(result["ready_for_analysis"])
            self.assertTrue(result["frame_exhausted"])
            self.assertFalse(result["target_reached"])
            self.assertEqual(result["comparable_users"], 0)

    def test_incomplete_or_altered_history_rejected_before_analysis_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = fixtures.PublicationTests().freeze_fixture(Path(tmp))
            annotations.next_batch(setting, plan, study, reg)
            sample = read_csv(study / "annotations/cohort_0001/sample.csv")
            ranked, corpus = read_csv(study / "eligible_users.csv"), read_csv(study / "corpus.csv")
            validate_histories(sample, ranked, corpus)
            with self.assertRaisesRegex(ValueError, "Faltan o sobran"):
                validate_histories(sample.iloc[:-1], ranked, corpus)
            with self.assertRaisesRegex(ValueError, "difiere"):
                validate_histories(sample.assign(text="changed"), ranked, corpus)
            # A final analysis cannot proceed using only AI proposals.
            fixtures.PublicationTests().proposals(study, "cohort_0001", reg)
            (Path(tmp) / "AGENTS.md").write_text("<!-- BEGIN GENERATED RESULTS COMPARISON -->\nhistory\n<!-- END GENERATED RESULTS COMPARISON -->\n")
            with self.assertRaisesRegex(ValueError, "incompleta"):
                analysis.analyze(setting, plan, study, reg, stage="final")
            self.assertFalse((setting["outputs"] / study.name / "analysis_final").exists())

    def test_final_analysis_hand_computed_neutral_denominator_null_and_negative(self):
        for outcome, expected, evidence in [(None, 1.5, "positive_relative_favoritism"), ("null", 0., "inconclusive"),
                                             ("negative", -1.5, "negative_relative_favoritism")]:
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                setting, plan, parent, study, reg = fixtures.PublicationTests().freeze_fixture(root)
                annotations.next_batch(setting, plan, study, reg)
                self.complete_synthetic_batch(study, reg, outcome=outcome)
                agents = root / "AGENTS.md"
                agents.write_text("<!-- BEGIN GENERATED RESULTS COMPARISON -->\nhistorical sentinel\n<!-- END GENERATED RESULTS COMPARISON -->\n")
                reserved_hash = sha256(parent / "annotations/gold.csv")
                result = analysis.analyze(setting, plan, study, reg, stage="final")
                summary = json.loads((result / "summary.json").read_text())
                user = read_csv(result / "primary_user_scores.csv").iloc[0]
                self.assertAlmostEqual(float(user.gap), expected)
                self.assertEqual(int(float(user.N_out)), 2)  # one neutral still belongs in denominator
                self.assertEqual(summary["precision"]["gap_evidence"], evidence)
                self.assertEqual(summary["measurement_basis"], "human_annotations")
                self.assertFalse(summary["production_enabled"])
                self.assertFalse(summary["automatic_expansion_enabled"])
                self.assertEqual(summary["screened_comments"], 5)
                self.assertTrue((result / "annotation_support.csv").exists())
                self.assertTrue((result / "event_composition.csv").exists())
                self.assertTrue((study / "annotations/cohort_0001/reference.json").exists())
                self.assertIn("historical sentinel", agents.read_text())
                self.assertIn("IC95% gap", agents.read_text())
                self.assertEqual(sha256(parent / "annotations/gold.csv"), reserved_hash)
                self.assertFalse((parent / "model/test_opened.json").exists())
                self.assertFalse((study / "training").exists())
                with self.assertRaises(FileExistsError):
                    analysis.analyze(setting, plan, study, reg, stage="final")

    def test_precision_failure_not_relabelled_as_success_or_absence(self):
        def assess(low, high, status="estimated"):
            return precision_assessment(pd.DataFrame([dict(contrast="gap", ci_low=low, ci_high=high, status=status)]), .2)
        wide = assess(-.5, .8)
        self.assertFalse(wide["precision_target_met"])
        self.assertEqual(wide["gap_evidence"], "inconclusive")
        self.assertEqual(assess(.1, 1.)["gap_evidence"], "positive_relative_favoritism")
        self.assertFalse(assess(.1, 1.)["precision_target_met"])
        self.assertTrue(assess(-.1, .1)["precision_target_met"])
        self.assertEqual(assess(-.1, .1)["gap_evidence"], "inconclusive")
        self.assertIsNone(assess(float("nan"), float("nan"), "insufficient_coverage")["precision_target_met"])

    def test_exhausted_no_comparables_has_explicit_exclusions_and_no_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setting, plan, _, study, reg = fixtures.PublicationTests().freeze_fixture(root)
            plan = {**plan, "comparable_users":2}
            for i in (1, 2):
                annotations.next_batch(setting, plan, study, reg, stage="final")
                self.complete_synthetic_batch(study, reg, f"cohort_{i:04d}", empty=True)
            (root / "AGENTS.md").write_text("<!-- BEGIN GENERATED RESULTS COMPARISON -->\nhistory\n<!-- END GENERATED RESULTS COMPARISON -->\n")
            result = analysis.analyze(setting, plan, study, reg, stage="final")
            summary = json.loads((result / "summary.json").read_text())
            self.assertTrue(summary["frame_exhausted"])
            self.assertEqual(summary["comparable_users"], 0)
            self.assertIsNone(summary["gap"])
            self.assertEqual(summary["precision"]["precision_status"], "not_estimable")
            screened = read_csv(result / "screened_user_scores.csv")
            self.assertTrue(screened.exclusion_reasons.map(json.loads).map(lambda v:v==["no_known_evaluable_events"]).all())

    def test_unknown_mixed_and_absence_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, _, study, reg = fixtures.PublicationTests().freeze_fixture(Path(tmp))
            corpus = read_csv(study / "corpus.csv")
            sample = corpus.loc[corpus.comment_id.isin(["extra0", "extra2", "extra3"])].copy()
            sample["annotation_json"] = sample.comment_id.map({
                "extra0":json.dumps([dict(target_id="a", valence="mixed")]),
                "extra2":json.dumps([dict(target_id="x", valence="negative")]), "extra3":"[]"})
            events = analysis.events_from_annotations(sample, reg)
            coverage, composition, support = coverage_tables(corpus, sample, events, {"other"}, reg)
            screened = support.loc[support.scope.eq("screened")]
            self.assertEqual(set(screened.target_group), {"izquierda", "unknown", "none"})
            self.assertEqual(set(composition.valence), {"mixed"})
            self.assertNotIn("neutral", set(screened.valence))
            self.assertEqual(int(coverage.loc[coverage.scope.eq("screened") & coverage.source.eq("all"), "comments"].iloc[0]), 3)


if __name__ == "__main__":
    unittest.main()
