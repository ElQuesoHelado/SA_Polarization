"""Operational checks use isolated synthetic samples and never real confirmations."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from polarization_pipeline.targeted.common import read_csv,sha256
from polarization_pipeline.targeted.publication import runtime,batches,annotations,capture_audit
from polarization_pipeline.targeted.publication.state import lock,verify_seal
import test_publication as fixtures
import test_local_preparation as local_fixtures


class OperationsTests(unittest.TestCase):
    def test_runtime_reports_stopped_even_when_recorded_phase_waits(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().fixture(Path(tmp))
            before={str(p):sha256(p) for p in Path(tmp).rglob('*') if p.is_file()}
            result=runtime.status(setting,study)
            self.assertFalse(result['controller_active'])
            self.assertEqual(before,{str(p):sha256(p) for p in Path(tmp).rglob('*') if p.is_file()})
            with lock(study/'advancement.lock'):
                self.assertTrue(runtime.status(setting,study)['controller_active'])

    def test_heartbeat_marks_exit_without_leaving_a_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            study=Path(tmp)
            with runtime.heartbeat(study):
                self.assertTrue(json.loads((study/'advancement_heartbeat.json').read_text())['running'])
            self.assertFalse(json.loads((study/'advancement_heartbeat.json').read_text())['running'])

    def test_services_use_argument_arrays_and_reuse_active_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().fixture(Path(tmp))
            result=Mock(returncode=0,stdout='inactive\n')
            with patch.object(runtime.subprocess,'run',return_value=result) as run:
                report=runtime.start_services(setting,study,setting['_config_path'],9000)
            launches=[c.args[0] for c in run.call_args_list if c.args[0][0]=='systemd-run']
            self.assertEqual(len(launches),2)
            self.assertTrue(all('--user' in args and '--property=Restart=no' in args for args in launches))
            self.assertFalse(report['restart_after_reboot'])
            with patch.object(runtime.subprocess,'run',return_value=Mock(returncode=0,stdout='active\n')) as run:
                self.assertEqual(runtime.start_services(setting,study,setting['_config_path'],9000)['services']['advance'],'already_active')
                self.assertEqual(run.call_count,2)

    def test_services_refuse_duplicate_unmanaged_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().fixture(Path(tmp))
            with lock(study/'advancement.lock'):
                with patch.object(runtime.subprocess,'run',return_value=Mock(returncode=0,stdout='inactive\n')):
                    with self.assertRaises(RuntimeError):runtime.start_services(setting,study,setting['_config_path'],9000)

    def test_batch_boundaries_cover_every_row_once(self):
        values=[i for n in range(1,5) for i in batches.indices(151,n)]
        self.assertEqual(values,list(range(151)))
        for n in [0,-1,5,True]:
            with self.assertRaises(ValueError):batches.indices(151,n)

    def test_blind_export_has_only_text_and_id_and_reuses_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            annotations.init_benchmark(study)
            result=batches.export(study,'benchmark')
            folder=Path(result['folder']);verify_seal(folder)
            rows=json.loads((folder/'reading.json').read_text())
            self.assertTrue(all(set(r)=={'sample_id','text'} for r in rows))
            self.assertFalse((folder/'proposal_template.json').exists())
            before={str(p):sha256(p) for p in folder.iterdir() if p.is_file()}
            batches.export(study,'benchmark')
            self.assertEqual(before,{str(p):sha256(p) for p in folder.iterdir() if p.is_file()})

    def test_cohort_template_is_unannotated_and_preserves_complete_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            annotations.next_batch(setting,plan,study,reg)
            result=batches.export(study,'cohort_0001')
            folder=Path(result['folder']);template=json.loads((folder/'proposal_template.json').read_text())
            self.assertTrue(all(r['annotations'] is None for r in template['proposals']))
            sample=read_csv(study/'annotations/cohort_0001/sample.csv').set_index('sample_id')
            for item in json.loads((folder/'reading.json').read_text()):
                self.assertEqual(item['text'],sample.loc[item['sample_id'],'text'])
            self.assertTrue(read_csv(study/'annotations/cohort_0001/human_review.csv').review_complete.eq('').all())
            template['origin']='synthetic proposal template'
            with self.assertRaisesRegex(ValueError,'pendiente'):annotations.import_proposals(study,'cohort_0001',template,reg)

    def test_blind_review_confirms_only_selected_tanda_then_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().freeze_fixture(Path(tmp))
            annotations.init_benchmark(study)
            with patch.object(batches,'SIZE',2):
                with patch('polarization_pipeline.targeted.review.edit_items',return_value=[]):
                    with patch('builtins.input',side_effect=['synthetic human','s','s']):
                        annotations.review(study,'benchmark',reg)
            form=read_csv(study/'annotations/benchmark/human_review.csv')
            self.assertEqual(form.review_complete.eq('true').tolist(),[True,True,False,False])
            with patch.object(batches,'SIZE',2):
                with patch('polarization_pipeline.targeted.review.edit_items',return_value=[]):
                    with patch('builtins.input',side_effect=['synthetic human','s','s']):
                        annotations.review(study,'benchmark',reg)
            self.assertTrue(read_csv(study/'annotations/benchmark/human_review.csv').review_complete.eq('true').all())

    def test_capture_audit_counts_new_replies_and_leaves_final_samples_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=local_fixtures.LocalPreparationTests().fixture(Path(tmp))
            setting,plan,parent,study,reg=args
            result=capture_audit.run(setting,plan,study,reg)
            self.assertEqual(result['new_comments'],1)
            self.assertEqual(result['new_replies'],1)
            self.assertEqual(result['parent_links']['parent_present'],1)
            self.assertEqual(result['parent_links']['parent_other_video'],0)
            self.assertEqual(result['structural_candidates_historical'],2)
            verify_seal(Path(result['report']))
            for name in ['freeze.json','corpus.csv','benchmark.csv','annotations']:
                self.assertFalse((study/name).exists())
            self.assertFalse((parent/'model/test_opened.json').exists())

    def test_review_does_not_create_an_unprepared_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting,plan,parent,study,reg=fixtures.PublicationTests().fixture(Path(tmp))
            with self.assertRaises(FileNotFoundError):annotations.review(study,'benchmark',reg)
            self.assertFalse((study/'annotations').exists())
