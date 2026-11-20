from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from polarization_pipeline.targeted.annotations import training_pairs, check_development_extraction
from polarization_pipeline.targeted.assisted import (
    annotation_digest, check_review, import_proposals, import_review, initialize, verify_completed,
)
from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.registry import Matcher, registry_fingerprint
from polarization_pipeline.targeted.revision import load_inherited, registry_audit, reusable, revise


class RevisionTests(unittest.TestCase):
    def fixture(self, root):
        source = root / "original"
        folder = source / "annotations"
        folder.mkdir(parents=True)
        target = {"target_id": "a", "name": "Actor A", "aliases": ["Actor A"],
                  "entity_type": "political_actor", "target_group": "izquierda",
                  "valid_from": "2026-01-01", "valid_to": "2026-06-30", "sources": ["https://example.org/a"]}
        registry = root / "registry.json"
        atomic_json(registry, {"schema_version": 1, "version": "original", "status": "reviewed", "targets": [target]})
        rows = [{"sample_id": f"s{i}", "comment_id": f"c{i}", "post_id": f"v{i}",
                 "text": f"Actor A comentario {i}", "parent_text": "", "post_title": "Título",
                 "comment_published_at": "2026-04-01", "party": "neutral", "comment_type": "reply" if i % 5 == 0 else "top_level",
                 "pilot": i < 4, "split": "train" if i < 16 else "validation" if i < 20 else "test",
                 "sampling_probability": "0.5"} for i in range(24)]
        from polarization_pipeline.targeted.annotations import text_key
        import hashlib
        for row in rows:
            row["sample_id"] = hashlib.sha256(f"annotation:{row['comment_id']}".encode()).hexdigest()[:20]
        sample = pd.DataFrame(rows)
        sample.to_csv(folder / "sampling_manifest.csv", index=False)
        for i in (1, 2):
            sample.assign(annotation_json="", review_complete="").to_csv(folder / f"reviewer_{i}.csv", index=False)
        fresh = [{**rows[0], "comment_id": f"fresh{i}", "post_id": f"freshv{i}",
                  "text": f"Actor A comentario nuevo {i}", "comment_type": "reply" if i % 5 == 0 else "top_level"}
                 for i in range(200)]
        corpus = pd.DataFrame(rows + fresh)
        corpus.loc[corpus.comment_type.eq("top_level")].to_csv(source / "corpus_main.csv", index=False)
        corpus.to_csv(source / "corpus_panel.csv", index=False)
        atomic_json(folder / "manifest.json", {"registry_sha256": registry_fingerprint(registry),
            "sampling_sha256": sha256(folder / "sampling_manifest.csv"), "corpus_main_sha256": sha256(source / "corpus_main.csv"),
            "status": "awaiting_two_human_reviewers", "model_test_opened": False})
        old_settings = {"registry": registry}
        initialize(old_settings, source)
        items = [{"target_id": "a", "valence": "positive", "mention_start": 0, "mention_end": 7}]
        batch = root / "batch.json"
        atomic_json(batch, {"origin": "synthetic_test", "proposals": [{"sample_id": x["sample_id"], "annotations": items} for x in rows]})
        import_proposals(old_settings, source, batch)
        human = read_csv(folder / "human_review.csv")
        for column, value in {"annotation_json": json.dumps(items), "review_complete": "true", "reviewed_at": "2026-01-01",
                              "reviewer_id": "synthetic_test", "decision": "accepted", "proposal_sha256": annotation_digest(items)}.items():
            human[column] = value
        human.to_csv(folder / "human_review.csv", index=False)
        revised_registry = root / "registry_v2.json"
        atomic_json(revised_registry, {"schema_version": 1, "version": "v2", "status": "reviewed",
            "matching": {"version": 2, "ignore_usernames": True}, "targets": [target]})
        settings = {"registry": revised_registry, "seed": 42, "sampling_split_seed": 43,
                    "reuse_reviewed_development": True, "annotation_comments": 20, "annotation_replies": 4,
                    "quality": {"target_precision": .9, "target_recall": .8}}
        return old_settings, settings, source

    def test_matcher_longest_unicode_spaces_and_usernames(self):
        base = {"target_id": "a", "name": "Actor A", "aliases": ["José", "José Pérez"], "entity_type": "political_actor",
                "target_group": "unknown", "valid_from": "2026-01-01", "valid_to": "2026-12-31"}
        other = {**base, "target_id": "b", "name": "Otro", "aliases": ["Pérez"]}
        matcher = Matcher({"targets": [base, other], "matching": {"version": 2, "ignore_usernames": True}})
        text = "@José-Pérez Jo\u0301se\u0301   Pérez apoyado"
        found = matcher.find(text, "2026-04-01")
        self.assertEqual([x["target_id"] for x in found], ["a"])
        self.assertEqual(text[found[0]["mention_start"]:found[0]["mention_end"]], "Jo\u0301se\u0301   Pérez")
        self.assertEqual(matcher.find("@José-Pérez"), [])

    def test_reuse_requires_explicit_identity_and_unchanged_context(self):
        registry = {"targets": [{"target_id": "a", "name": "Actor A", "aliases": ["Actor A"],
                     "annotation_ids": ["unregistered:Actor A"], "entity_type": "political_actor", "target_group": "unknown",
                     "valid_from": "2026-01-01", "valid_to": "2026-12-31"}]}
        row = {"text": "Actor A malo", "comment_published_at": "2026-04-01"}
        items = [{"target_id": "unregistered:Actor A", "valence": "negative", "mention_start": 0, "mention_end": 7}]
        translated, reason = reusable(row, row, items, registry)
        self.assertEqual(reason, "compatible")
        self.assertEqual(translated[0]["valence"], "negative")
        self.assertEqual(items[0]["target_id"], "unregistered:Actor A")
        self.assertEqual(reusable({**row, "parent_text": "nuevo"}, row, items, registry)[1], "text_or_context_changed")
        contextual = {**row, "text": "el hombre malo"}
        self.assertEqual(reusable(contextual, contextual, items, registry)[1], "unmapped_or_contextual_identity")
        self.assertEqual(reusable(row, row, [], registry)[1], "new_candidate_requires_human_check")

    def test_revision_preserves_original_and_does_not_confirm_humans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, settings, source = self.fixture(root)
            before = {x.relative_to(source).as_posix(): sha256(x) for x in source.rglob("*") if x.is_file()}
            destination = root / "v2"
            report = revise(settings, destination, source, old)
            self.assertGreater(report["inherited"], 0)
            self.assertGreaterEqual(report["new_comments"], 5)
            human = read_csv(destination / "annotations/human_review.csv")
            self.assertTrue(human.review_complete.eq("").all())
            self.assertTrue(human.annotation_json.eq("").all())
            sample = read_csv(destination / "annotations/sampling_manifest.csv")
            self.assertFalse(set(sample.loc[sample.split.eq("test")].post_id) & set(read_csv(source / "annotations/sampling_manifest.csv").post_id))
            self.assertEqual(sample.groupby("post_id").split.nunique().max(), 1)
            self.assertEqual(sample.split.value_counts().to_dict(), {"train": 12, "test": 5, "validation": 3})
            self.assertTrue(sample.sampling_probability.astype(float).between(0, 1, inclusive="right").all())
            self.assertEqual(before, {x.relative_to(source).as_posix(): sha256(x) for x in source.rglob("*") if x.is_file()})
            after = {str(x): sha256(x) for x in destination.rglob("*") if x.is_file()}
            diagnostics = check_review(settings, destination)
            self.assertEqual(diagnostics["pending"], report["pending"])
            self.assertFalse(diagnostics["ready_to_import"])
            for split in diagnostics["development_extraction"].values():
                if not split["complete"]:
                    self.assertIsNone(split["precision"])
            self.assertEqual(after, {str(x): sha256(x) for x in destination.rglob("*") if x.is_file()})
            with self.assertRaises(ValueError):
                training_pairs(settings, destination)
            with self.assertRaises(FileExistsError):
                revise(settings, destination, source, old)

    def test_source_tampering_invalidates_inherited_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, settings, source = self.fixture(root); destination = root / "v2"
            revise(settings, destination, source, old)
            path = destination / "inheritance_source/annotations/human_review.csv"
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "fuente.*heredada"):
                load_inherited(settings, destination, read_csv(destination / "annotations/sampling_manifest.csv"))

    def test_prior_videos_cannot_be_final_test_even_if_sampling_hash_is_updated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, settings, source = self.fixture(root); destination = root / "v2"
            revise(settings, destination, source, old)
            path = destination / "annotations/sampling_manifest.csv"; sample = read_csv(path)
            sample.loc[sample.split.eq("test"), "post_id"] = "v0"
            sample.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "prueba contiene videos"):
                load_inherited(settings, destination, sample)

    def test_completed_revision_roundtrip_and_no_final_test_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, settings, source = self.fixture(root); destination = root / "v2"
            revise(settings, destination, source, old)
            folder = destination / "annotations"; sample = read_csv(folder / "sampling_manifest.csv")
            inherited = load_inherited(settings, destination, sample)
            items = [{"target_id": "a", "valence": "positive", "mention_start": 0, "mention_end": 7}]
            atomic_json(root / "new_batch.json", {"origin": "synthetic_test", "proposals": [
                {"sample_id": key, "annotations": items} for key in sample.sample_id if key not in inherited]})
            import_proposals(settings, destination, root / "new_batch.json")
            human = read_csv(folder / "human_review.csv")
            mask = ~human.sample_id.isin(inherited)
            for column, value in {"annotation_json": json.dumps(items), "review_complete": "true", "reviewed_at": "2026-01-01",
                "reviewer_id": "synthetic_test", "decision": "accepted", "proposal_sha256": annotation_digest(items)}.items():
                human.loc[mask, column] = value
            human.to_csv(folder / "human_review.csv", index=False)
            diagnostics = check_review(settings, destination)
            self.assertTrue(diagnostics["ready_to_import"])
            self.assertNotIn("test", diagnostics["development_extraction"])
            import_review(settings, destination, pilot_only=True)
            import_review(settings, destination)
            verify_completed(settings, destination)
            self.assertEqual(len(training_pairs(settings, destination)), 20)
            self.assertTrue(read_csv(folder / "human_review.csv").loc[human.sample_id.isin(inherited), "review_complete"].eq("").all())
            import tarfile
            from polarization_pipeline.targeted.common import config
            from polarization_pipeline.targeted.remote import prepare_job
            remote_settings = config("config/targeted_v2.toml")
            remote_settings["registry"] = settings["registry"]
            stage = prepare_job(remote_settings, destination, "train")
            with tarfile.open(stage / "dataset/targeted_payload.tar.gz") as archive:
                self.assertFalse(any("inheritance_source" in x or x.endswith("human_review.csv") for x in archive.getnames()))
                archive.extractall(root / "remote", filter="data")
            remote_run = root / "remote/run"
            self.assertNotIn("test", set(read_csv(remote_run / "annotations/gold.csv").split))
            self.assertEqual(len(training_pairs(remote_settings, remote_run)), 15)

    def test_registry_audit_uses_development_only_and_includes_missed_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, settings, source = self.fixture(root)
            path = source / "annotations/human_review.csv"; human = read_csv(path)
            # Synthetic test annotation modification with a coherent proposal receipt.
            row = human.iloc[0]; items = json.loads(row.annotation_json)
            items.append({"target_id": "unregistered:Omitido", "valence": "negative", "mention_start": 8, "mention_end": 18})
            human.loc[0, "annotation_json"] = json.dumps(items); human.loc[0, "decision"] = "modified"; human.to_csv(path, index=False)
            result = registry_audit(settings, source, old)
            self.assertLess(result["splits"]["train"]["recall"], 1)
            self.assertEqual(set(result["splits"]), {"train", "validation"})

    def test_development_failure_blocks_before_consuming_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, settings, source = self.fixture(root)
            sample = read_csv(source / "annotations/sampling_manifest.csv")
            sample["annotation_json"] = json.dumps([{"target_id": "unregistered:omitido", "valence": "positive"}])
            with self.assertRaisesRegex(ValueError, "no entrenar ni abrir prueba"):
                check_development_extraction(settings, sample)
            item = [{"target_id": "a", "valence": "positive"}]
            sample.loc[sample.split.ne("test"), "annotation_json"] = json.dumps(item)
            # A deliberately bad reserved test is never scored by this development guard.
            check_development_extraction(settings, sample)
            self.assertFalse((source / "model/test_opened.json").exists())

    def test_partial_review_does_not_report_biased_extraction_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, settings, source = self.fixture(root)
            path = source / "annotations/human_review.csv"
            human = read_csv(path); human.loc[0, "review_complete"] = ""
            human.to_csv(path, index=False)
            diagnostics = check_review(old, source)
            self.assertFalse(diagnostics["development_extraction"]["train"]["complete"])
            self.assertIsNone(diagnostics["development_extraction"]["train"]["precision"])
            self.assertIsNone(diagnostics["development_extraction"]["train"]["recall"])

    def test_contextual_source_is_not_silently_inherited_as_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, settings, source = self.fixture(root)
            revise(settings, root / "first", source, old)
            sample = read_csv(root / "first/annotations/sampling_manifest.csv")
            inherited = read_csv(root / "first/annotations/inherited_reviews.csv")
            original = read_csv(source / "annotations/sampling_manifest.csv").set_index("sample_id")
            key = next(k for k in inherited.sample_id if sample.set_index("sample_id").loc[k, "split"] == "train" and original.loc[k, "split"] == "train")
            atomic_json(source / "annotations/evidence_policy.json", {"schema_version": 1, "main": "explicit_only",
                "sampling_sha256": sha256(source / "annotations/sampling_manifest.csv"),
                "contextual_targets": [{"sample_id": key, "target_id": "a", "reason": "synthetic contextual source"}]})
            revise(settings, root / "second", source, old)
            self.assertNotIn(key, set(read_csv(root / "second/annotations/inherited_reviews.csv").sample_id))


if __name__ == "__main__":
    unittest.main()
