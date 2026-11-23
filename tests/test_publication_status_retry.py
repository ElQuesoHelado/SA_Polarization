"""Transient read failures must never cause a repeated remote submission."""
import unittest
from unittest.mock import patch
from polarization_pipeline.targeted.publication import remote

class ReadOnlyStatusRetryTests(unittest.TestCase):
    def test_two_temporary_errors_then_complete_use_same_pinned_reference(self):
        args=['kernels','status','owner/training/2']
        with patch.object(remote,'_kaggle',side_effect=[RuntimeError('transport'),RuntimeError('transport'),'COMPLETE']) as query, \
             patch.object(remote.time,'sleep') as pause,patch.object(remote,'start_job') as push:
            self.assertEqual(remote.query_status({},args),'COMPLETE')
        self.assertEqual(query.call_count,3)
        self.assertTrue(all(call.args[1]==args for call in query.call_args_list))
        self.assertEqual([call.args for call in pause.call_args_list],[(30,),(30,)])
        push.assert_not_called()

    def test_exhausted_queries_stop_after_three_attempts(self):
        with patch.object(remote,'_kaggle',side_effect=RuntimeError('transport')) as query, \
             patch.object(remote.time,'sleep') as pause:
            with self.assertRaises(RuntimeError):remote.query_status({},['datasets','status','owner/data','--format','json'])
        self.assertEqual(query.call_count,3);self.assertEqual(pause.call_count,2)

    def test_reported_worker_error_is_returned_without_retry(self):
        with patch.object(remote,'_kaggle',return_value='ERROR') as query,patch.object(remote.time,'sleep') as pause:
            self.assertEqual(remote.query_status({},['kernels','status','owner/train/2']),'ERROR')
        query.assert_called_once();pause.assert_not_called()

    def test_submissions_and_downloads_are_never_retryable(self):
        for args in [['kernels','push'],['datasets','version'],['kernels','output'],['kernels','logs']]:
            with self.subTest(args=args),patch.object(remote,'_kaggle') as query:
                with self.assertRaises(ValueError):remote.query_status({},args)
                query.assert_not_called()
