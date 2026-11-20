"""Incremental preparation must preserve the frozen sampling inputs exactly."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.publication import data, local_preparation as local
import test_publication as fixtures


class LocalPreparationTests(unittest.TestCase):
    def fixture(self, root, complete=True):
        setting, plan, parent, study, reg = fixtures.PublicationTests().fixture(root)
        historical = read_csv(study / 'historical.csv')
        plan['benchmark_counts'] = [2, 1, 1, 1]
        for i, video in enumerate(read_csv(study / 'videos.csv').to_dict('records')):
            comments = {}
            if i == 0:
                duplicate = historical.loc[historical.post_id.eq(video['post_id'])].iloc[0].to_dict()
                duplicate.update(text='Actor B edited', like_count=2, reply_count=0)
                comments[duplicate['comment_id']] = duplicate
                child = {**duplicate, 'comment_id': 'new_reply', 'parent_id': duplicate['comment_id'],
                         'text': 'Actor A nueva respuesta', 'comment_type': 'reply', 'like_count': 3}
                comments[child['comment_id']] = child
                comments['old'] = {**child, 'comment_id': 'old', 'comment_published_at': '2020-01-01T00:00:00Z'}
            atomic_json(study / 'raw_capture' / f"{video['post_id']}.json",
                        dict(status='complete' if complete else 'incomplete', video=video,
                             comments=comments, finished_at='2026-11-19T12:00:00Z'))
        return setting, plan, parent, study, reg

    def test_cached_and_uncached_freeze_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            left = self.fixture(Path(a)); right = self.fixture(Path(b))
            setting, plan, parent, study, reg = left
            first = local.prepare_pass(setting, plan, study, reg)
            self.assertEqual(first['new_comments'], 1)
            self.assertEqual(first['excluded_capture_rows'], 1)
            self.assertEqual(first['repeated_versions'], 1)
            for name in ('corpus.csv', 'benchmark.csv', 'eligible_users.csv', 'annotations'):
                self.assertFalse((study / name).exists())
            with patch.object(local.Matcher, 'find', side_effect=AssertionError('warm cache rematched')):
                union, versions, exclusions, candidates, stats = local.assemble(setting, study, reg)
                self.assertEqual(stats['cache_misses'], 0)
                data.freeze(*left)
            data.freeze(*right, use_cache=False)
            for name in ('corpus.csv', 'recapture_versions.csv', 'capture_exclusions.csv', 'eligible_users.csv', 'benchmark.csv'):
                self.assertEqual((study / name).read_bytes(), (right[3] / name).read_bytes(), name)
            row = read_csv(study / 'corpus.csv').set_index('comment_id').loc['new_reply']
            self.assertEqual(row.parent_text, 'Actor B edited')
            self.assertFalse((parent / 'model/test_opened.json').exists())

    def test_partial_becomes_complete_and_unchanged_pass_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp), complete=False)
            first = local.prepare_pass(setting, plan, study, reg)
            pointer = study / 'local_preparation_cache/latest.json'
            before = (sha256(pointer), pointer.stat().st_mtime_ns)
            with patch.object(local.Matcher, 'find', side_effect=AssertionError('unchanged rematched')):
                self.assertEqual(local.prepare_pass(setting, plan, study, reg)['status'], 'unchanged')
            self.assertEqual(before, (sha256(pointer), pointer.stat().st_mtime_ns))
            capture = next((study / 'raw_capture').glob('*.json'))
            state = json.loads(capture.read_text()); state['status'] = 'complete'; atomic_json(capture, state)
            # Report timestamps may match at one-second resolution; use a deterministic new stamp.
            with patch.object(local, 'stamp', return_value='2026-11-19T12:00:01Z'):
                second = local.prepare_pass(setting, plan, study, reg)
            self.assertEqual(second['cache']['cache_hits'], 1)
            self.assertEqual(second['cache']['cache_misses'], 1)
            self.assertEqual(second['capture_status']['complete'], 1)
            self.assertEqual(first['cache']['capture_rows'], 0)

    def test_corrupt_fragment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            local.assemble(setting, study, reg)
            fragment = next((study / 'local_preparation_cache').rglob('rows.csv'))
            fragment.write_text(fragment.read_text() + 'tampered')
            with self.assertRaises(ValueError):
                local.assemble(setting, study, reg)

    def test_context_change_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            local.assemble(setting, study, reg)
            altered = copy.deepcopy(setting)
            altered['source']['youtube']['periods'] = []
            self.assertNotEqual(local.context(setting, reg), local.context(altered, reg))
            with patch.object(local.Matcher, 'find', wraps=local.Matcher.find, autospec=True) as matched:
                # A distinct version namespace has no hits, even for identical inputs.
                source = local.inventory(study)[0][0]
                _, _, hit = local.fragment(setting, study, reg, source, 'different_context')
                self.assertFalse(hit)
                self.assertGreater(matched.call_count, 0)

    def test_source_changed_after_inventory_is_deferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            source = local.inventory(study)[0][1]
            path = source[1]; path.write_text(path.read_text() + '\n')
            with self.assertRaises(local.SourceChanged):
                local.fragment(setting, study, reg, source, local.context(setting, reg))
            self.assertFalse((study / 'local_preparation_cache/latest.json').exists())

    def test_watch_stops_on_frozen_marker_and_has_separate_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            def finish(_):
                atomic_json(study / 'freeze.json', {'synthetic': True})
            with data.lock(setting['workspace'] / 'publication_collection.lock'):
                with patch.object(local.time, 'sleep', side_effect=finish):
                    self.assertEqual(local.run(setting, plan, study, reg, watch=True)['status'], 'snapshot_frozen')

    def test_mid_processing_source_change_is_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            source = local.inventory(study)[0][1]
            original = local.Matcher.find
            changed = False
            def change(matcher, text, date=''):
                nonlocal changed
                if not changed:
                    changed = True
                    source[1].write_text(source[1].read_text() + '\n')
                return original(matcher, text, date)
            with patch.object(local.Matcher, 'find', autospec=True, side_effect=change):
                with self.assertRaises(local.SourceChanged):
                    local.fragment(setting, study, reg, source, local.context(setting, reg))
            self.assertFalse((study / 'local_preparation_cache').exists())

    def test_conflicting_recapture_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            for path in (study / 'raw_capture').glob('*.json'):
                state = json.loads(path.read_text())
                if state['comments']:
                    first = next(iter(state['comments'].values()))
                    first['user_id'] = 'conflicting_author'
                    atomic_json(path, state)
                    break
            with self.assertRaises(ValueError):
                local.prepare_pass(setting, plan, study, reg)
            self.assertFalse((study / 'local_preparation_cache/latest.json').exists())

    def test_capture_mixed_dates_match_individual_filtering(self):
        from polarization_pipeline.targeted.common import in_window
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            setting, plan, parent, study, reg = self.fixture(Path(tmp))
            state = json.loads(next(path.read_text() for path in (study / 'raw_capture').glob('*.json')
                                    if json.loads(path.read_text())['comments']))
            comment = next(iter(state['comments'].values()))
            dates = ['2026-04-02T00:00:00Z', '2026-04-02T00:00:00.123Z', 'invalid', '2020-01-01']
            state['comments'] = {str(i): {**comment, 'comment_id': str(i), 'comment_published_at': date}
                                  for i, date in enumerate(dates)}
            periods = setting['source']['youtube']['periods']
            expected = [str(i) for i, date in enumerate(dates) if in_window(pd.Series([date]), periods).iloc[0]]
            rows, omitted = local.capture_rows(state, periods)
            self.assertEqual([r['comment_id'] for r in rows], expected)
            self.assertEqual(len(rows) + len(omitted), len(dates))
