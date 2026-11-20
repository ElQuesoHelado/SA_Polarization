from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from polarization_pipeline.targeted.annotations import training_pairs, import_annotations, export_annotations
from polarization_pipeline.targeted.assisted import initialize, import_proposals, import_review, verify_completed
from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.registry import registry_fingerprint
from polarization_pipeline.targeted.review import assisted_review, annotate


class AssistedTests(unittest.TestCase):
    def fixture(self, root):
        run = root / "run"
        folder = run / "annotations"
        folder.mkdir(parents=True)
        registry = root / "registry.json"
        atomic_json(registry, {"schema_version": 1, "version": "test", "status": "reviewed", "targets": [
            {"target_id": "a", "name": "Actor A", "aliases": ["Actor A"], "target_group": "izquierda", "entity_type": "political_actor",
             "valid_from": "2026-01-01", "valid_to": "2026-06-30", "sources": ["https://example.org/a"]}]})
        sample = pd.DataFrame([{"sample_id": f"s{i}", "comment_id": f"c{i}", "text": text,
            "parent_text": "", "post_title": "Título", "pilot": i == 1, "split": split,
            "post_id": f"v{i}", "sampling_probability": "1", "comment_published_at": "2026-04-01"}
            for i, text, split in [(1, "Actor A", "train"), (2, "Actor A!", "validation"), (3, "Sin objetivo", "test")]])
        sample.to_csv(folder / "sampling_manifest.csv", index=False)
        for i in (1, 2):
            sample.assign(annotation_json="", review_complete="").to_csv(folder / f"reviewer_{i}.csv", index=False)
        atomic_json(folder / "manifest.json", {"registry_sha256": registry_fingerprint(registry),
            "sampling_sha256": sha256(folder / "sampling_manifest.csv"), "status": "awaiting_two_human_reviewers"})
        return run, {"registry": registry, "quality": {"kappa": .70}}

    def proposals(self, run, settings):
        payload = {"origin": "synthetic fixture, not study annotations", "proposals": [
            {"sample_id": f"s{i}", "annotations": [{"target_id": "a", "valence": "positive", "mention_start": 0, "mention_end": 7}] if i < 3 else [], "note": "fixture"}
            for i in (1, 2, 3)]}
        path = run / "batch.json"
        atomic_json(path, payload)
        import_proposals(settings, run, path)
        return path

    def review_all(self, run, settings):
        with patch("builtins.input", side_effect=["a", "s"] * 3), redirect_stdout(io.StringIO()):
            assisted_review(settings, run)

    def test_proposals_do_not_confirm_humans_or_allow_training(self):
        with tempfile.TemporaryDirectory() as temp:
            run, settings = self.fixture(Path(temp))
            before = [sha256(run / f"annotations/reviewer_{i}.csv") for i in (1, 2)]
            initialize(settings, run)
            self.proposals(run, settings)
            human = read_csv(run / "annotations/human_review.csv")
            self.assertTrue(human.review_complete.eq("").all())
            self.assertTrue(human.annotation_json.eq("").all())
            self.assertEqual(before, [sha256(run / f"annotations/reviewer_{i}.csv") for i in (1, 2)])
            with self.assertRaisesRegex(ValueError, "confirmar humanamente"):
                training_pairs(settings, run)
            with self.assertRaisesRegex(ValueError, "incompleta"):
                import_review(settings, run, pilot_only=True)
            with self.assertRaisesRegex(ValueError, "assisted-import"):
                import_annotations(settings, run)
            with self.assertRaisesRegex(ValueError, "assisted-review"):
                annotate(settings, run, 1)

    def test_correction_save_resume_and_missing_target(self):
        with tempfile.TemporaryDirectory() as temp:
            run, settings = self.fixture(Path(temp))
            initialize(settings, run)
            self.proposals(run, settings)
            with patch("builtins.input", side_effect=["e", "a", "Actor A", "negative", "", "s", "q"]), redirect_stdout(io.StringIO()):
                assisted_review(settings, run)
            human = read_csv(run / "annotations/human_review.csv")
            self.assertEqual(human.decision.tolist(), ["modified", "", ""])
            self.assertEqual(json.loads(human.annotation_json[0])[0]["valence"], "negative")
            self.assertEqual(human.review_complete.tolist(), ["true", "", ""])
            with patch("builtins.input", side_effect=["a", "s", "a", "s"]), redirect_stdout(io.StringIO()):
                assisted_review(settings, run)
            with redirect_stdout(io.StringIO()):
                import_review(settings, run, pilot_only=True)
            import_review(settings, run)
            pairs = training_pairs(settings, run)
            self.assertEqual(set(pairs.label), {"negative", "positive"})
            report = json.loads((run / "annotations/assisted_review_report.json").read_text())
            self.assertEqual(report["modified"], 1)
            self.assertIsNone(report["interhuman_agreement"])
            with self.assertRaisesRegex(ValueError, "cerrada"):
                assisted_review(settings, run)

    def test_cancel_does_not_save_and_duplicate_batch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            run, settings = self.fixture(Path(temp))
            initialize(settings, run)
            path = self.proposals(run, settings)
            with patch("builtins.input", side_effect=["a", "n", "q"]), redirect_stdout(io.StringIO()):
                assisted_review(settings, run)
            self.assertTrue(read_csv(run / "annotations/human_review.csv").review_complete.eq("").all())
            before = sha256(run / "annotations/ai_proposals.csv")
            with self.assertRaisesRegex(ValueError, "sobrescribir"):
                import_proposals(settings, run, path)
            self.assertEqual(before, sha256(run / "annotations/ai_proposals.csv"))

    def test_pilot_is_required_and_changed_review_invalidates_training(self):
        with tempfile.TemporaryDirectory() as temp:
            run, settings = self.fixture(Path(temp))
            initialize(settings, run)
            self.proposals(run, settings)
            self.review_all(run, settings)
            with self.assertRaisesRegex(ValueError, "piloto"):
                import_review(settings, run)
            with redirect_stdout(io.StringIO()):
                import_review(settings, run, pilot_only=True)
            import_review(settings, run)
            verify_completed(settings, run)
            with (run / "annotations/human_review.csv").open("a") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "cambiaron"):
                training_pairs(settings, run)

    def test_seed_registry_is_allowed_for_proposals_but_not_final_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            run, settings = self.fixture(Path(temp))
            content = json.loads(settings["registry"].read_text())
            content["status"] = "seed_requires_reviewer_audit"
            atomic_json(settings["registry"], content)
            initialize(settings, run)
            self.proposals(run, settings)
            self.review_all(run, settings)
            with redirect_stdout(io.StringIO()):
                import_review(settings, run, pilot_only=True)
            with self.assertRaisesRegex(ValueError, "status=reviewed"):
                import_review(settings, run)
            with self.assertRaisesRegex(ValueError, "trabajo asistido"):
                export_annotations(settings, run, refresh_unreviewed=True)

    def test_changed_proposal_file_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            run, settings = self.fixture(Path(temp))
            initialize(settings, run)
            self.proposals(run, settings)
            with (run / "annotations/ai_proposals.csv").open("a") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "propuestas cambiaron"):
                assisted_review(settings, run)

    def test_training_package_withholds_test_labels_and_verifies_receipt(self):
        import tarfile
        from polarization_pipeline.targeted.common import config
        from polarization_pipeline.targeted.remote import prepare_job
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, settings = self.fixture(root)
            initialize(settings, run)
            self.proposals(run, settings)
            self.review_all(run, settings)
            with redirect_stdout(io.StringIO()):
                import_review(settings, run, pilot_only=True)
            import_review(settings, run)
            pd.DataFrame({"comment_id": ["c1", "c2", "c3"]}).to_csv(run / "corpus_main.csv", index=False)
            remote_settings = config()
            remote_settings["registry"] = settings["registry"]
            stage = prepare_job(remote_settings, run, "train")
            destination = root / "remote"
            with tarfile.open(stage / "dataset/targeted_payload.tar.gz") as archive:
                self.assertNotIn("run/annotations/ai_proposals.csv", archive.getnames())
                self.assertNotIn("run/annotations/human_review.csv", archive.getnames())
                archive.extractall(destination, filter="data")
            remote_run = destination / "run"
            gold = read_csv(remote_run / "annotations/gold.csv")
            self.assertNotIn("test", set(gold.split))
            self.assertNotIn("s3", set(gold.sample_id))
            receipt = remote_run / "annotations/assisted_training_receipt.json"
            self.assertTrue(json.loads(receipt.read_text())["test_labels_withheld"])
            pairs = training_pairs(settings, remote_run)
            self.assertEqual(len(pairs), 2)
            receipt.write_text("{}")
            with self.assertRaisesRegex(ValueError, "Recibo"):
                training_pairs(settings, remote_run)

    def test_contextual_reference_stays_out_of_primary_gold_without_changing_human(self):
        with tempfile.TemporaryDirectory() as temp:
            run, settings = self.fixture(Path(temp))
            initialize(settings, run)
            self.proposals(run, settings)
            self.review_all(run, settings)
            folder = run / "annotations"
            before = sha256(folder / "human_review.csv")
            policy = {"schema_version": 1, "main": "explicit_only", "sampling_sha256": sha256(folder / "sampling_manifest.csv"),
                      "contextual_targets": [{"sample_id": "s1", "target_id": "a", "reason": "Synthetic contextual fixture"}]}
            atomic_json(folder / "evidence_policy.json", policy)
            with redirect_stdout(io.StringIO()):
                import_review(settings, run, pilot_only=True)
            import_review(settings, run)
            self.assertEqual(before, sha256(folder / "human_review.csv"))
            gold = read_csv(folder / "gold.csv").set_index("sample_id")
            context = read_csv(folder / "contextual_annotations.csv").set_index("sample_id")
            self.assertEqual(json.loads(gold.loc["s1"].annotation_json), [])
            self.assertEqual(json.loads(context.loc["s1"].annotation_json)[0]["target_id"], "a")
            pairs = training_pairs(settings, run)
            # A matcher hit outside eligible gold is a disambiguation negative, never a positive contextual label.
            self.assertEqual(pairs.set_index("sample_id").loc["s1"].label, "not_evaluable")
            self.assertEqual(pairs.set_index("sample_id").loc["s2"].label, "positive")
            policy["contextual_targets"] = []
            atomic_json(folder / "evidence_policy.json", policy)
            with self.assertRaisesRegex(ValueError, "política de evidencia cambió"):
                training_pairs(settings, run)

    def test_contextual_policy_cannot_exclude_an_unannotated_target(self):
        from polarization_pipeline.targeted.evidence import separate_evidence
        with tempfile.TemporaryDirectory() as temp:
            run, settings = self.fixture(Path(temp))
            folder = run / "annotations"
            atomic_json(folder / "evidence_policy.json", {"schema_version": 1, "main": "explicit_only",
                "sampling_sha256": sha256(folder / "sampling_manifest.csv"),
                "contextual_targets": [{"sample_id": "s1", "target_id": "b", "reason": "fixture"}]})
            with self.assertRaisesRegex(ValueError, "decisión humana cambió"):
                separate_evidence(run, {"s1": []})


if __name__ == "__main__":
    unittest.main()
