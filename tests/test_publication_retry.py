import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from polarization_pipeline.targeted.common import atomic_json, sha256
from polarization_pipeline.targeted.publication import remote


class RetryTests(unittest.TestCase):
    def fixture(self, root):
        stage = root / 'kaggle/train'; stage.mkdir(parents=True)
        job = dict(started=True, published=True, kernel_ref='owner/train/1', expected_version=1,
                   payload_sha256='unchanged', kernel_sha256='unchanged')
        atomic_json(stage / 'job_manifest.json', job)
        return stage, job

    def test_cancelled_retry_preserves_previous_attempt_and_pins_new_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); stage, job = self.fixture(root)
            def api(settings, args):
                if args[0] == 'quota': return json.dumps([dict(resource='GPU', remaining='29.86h')])
                if args[1] == 'logs': return ''
                return 'CANCEL_ACKNOWLEDGED'
            def start(*args):
                current = json.loads((stage / 'job_manifest.json').read_text())
                current.update(started=True, kernel_ref='owner/train/2')
                atomic_json(stage / 'job_manifest.json', current)
            with patch.object(remote, 'validate_job'), patch.object(remote, 'frozen_execution_package'), \
                 patch.object(remote, '_kaggle', side_effect=api), patch.object(remote, 'start_job', side_effect=start) as push:
                ref = remote.retry(dict(kaggle={}), dict(model_extension_protocol='yes', kaggle={}), root, 'train')
            self.assertEqual(ref, 'owner/train/2'); push.assert_called_once()
            self.assertEqual(json.loads((stage / 'attempts/0001/job_manifest.json').read_text()), job)
            self.assertEqual(json.loads((stage / 'attempts/0001/retry.json').read_text())['state'], 'submitted')

    def test_running_or_partially_executed_job_is_not_retried(self):
        for status, logs in [('QUEUED', ''), ('CANCEL_ACKNOWLEDGED', 'epoch=1')]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); self.fixture(root)
                with patch.object(remote, 'validate_job'), patch.object(remote, 'start_job') as push, \
                     patch.object(remote, '_kaggle', side_effect=lambda s,a: logs if a[1]=='logs' else status):
                    with self.assertRaises(ValueError):
                        remote.retry(dict(kaggle={}), dict(model_extension_protocol='yes', kaggle={}), root, 'train')
                push.assert_not_called()
                self.assertFalse((root / 'kaggle/train/attempts').exists())

    def test_unknown_submission_is_preserved_and_blocks_a_second_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); stage, _ = self.fixture(root)
            def api(s, a):
                return json.dumps([dict(resource='GPU', remaining='20h')]) if a[0]=='quota' else '' if a[1]=='logs' else 'CANCEL_ACKNOWLEDGED'
            with patch.object(remote, 'validate_job'), patch.object(remote, 'frozen_execution_package'), \
                 patch.object(remote, '_kaggle', side_effect=api), patch.object(remote, 'start_job', side_effect=RuntimeError('transport')) as push:
                with self.assertRaises(RuntimeError):
                    remote.retry(dict(kaggle={}), dict(model_extension_protocol='yes', kaggle={}), root, 'train')
            self.assertEqual(json.loads((stage/'attempts/0001/retry.json').read_text())['state'], 'submission_unknown')
            with patch.object(remote, 'validate_job'), patch.object(remote, 'start_job') as push:
                with self.assertRaises(ValueError):
                    remote.retry(dict(kaggle={}), dict(model_extension_protocol='yes', kaggle={}), root, 'train')
                push.assert_not_called()

    def test_frozen_package_is_bound_to_original_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); stage,_=self.fixture(root)
            payload=stage/'payload'; (payload/'src/polarization_pipeline').mkdir(parents=True)
            code=payload/'src/polarization_pipeline/original.py'; code.write_text('original = True\n')
            atomic_json(payload/'payload_manifest.json', {'src/polarization_pipeline/original.py':sha256(code)})
            (stage/'dataset').mkdir(); archive=stage/'dataset/targeted_payload.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                tar.add(payload/'payload_manifest.json',arcname='payload_manifest.json')
            job=json.loads((stage/'job_manifest.json').read_text()); job['payload_sha256']=sha256(archive)
            atomic_json(stage/'job_manifest.json',job)
            self.assertEqual(remote.frozen_execution_package(root),code.parent)
            code.write_text('changed = True\n')
            atomic_json(payload/'payload_manifest.json', {'src/polarization_pipeline/original.py':sha256(code)})
            with self.assertRaisesRegex(ValueError,'Manifiesto'):
                remote.frozen_execution_package(root)

    def test_prediction_payload_uses_frozen_training_code_after_local_edits(self):
        import pandas as pd
        from polarization_pipeline.targeted.publication.state import seal
        from polarization_pipeline.targeted.publication import training
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);study=root/'study';stage,job=self.fixture(study)
            payload=stage/'payload';package=payload/'src/polarization_pipeline';package.mkdir(parents=True)
            (package/'original.py').write_text('frozen = True\n')
            atomic_json(payload/'payload_manifest.json',{'src/polarization_pipeline/original.py':sha256(package/'original.py')})
            (stage/'dataset').mkdir();archive=stage/'dataset/targeted_payload.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:tar.add(payload/'payload_manifest.json',arcname='payload_manifest.json')
            atomic_json(stage/'job_manifest.json',{**job,'payload_sha256':sha256(archive)})
            trained=study/'training';trained.mkdir();(trained/'weights').write_text('synthetic')
            seal(trained,['weights'])
            live=root/'src/polarization_pipeline';live.mkdir(parents=True)
            (live/'original.py').write_text('changed_local = True\n');(live/'analysis_only.py').write_text('must_not_upload = True\n')
            configs=[]
            for name in ['targeted.toml','pipeline.toml','registry.json']:
                path=root/name;path.write_text('synthetic');configs.append(path)
            settings=dict(_root=root,_config_path=configs[0],source_config=configs[1],registry=configs[2],
                kaggle=dict(dataset_id='old/data',training_kernel_id='old/train',inference_kernel_id='old/predict'),
                source=dict(kaggle=dict(dataset_id='legacy/data',kernel_id='legacy/kernel')))
            plan=dict(model_extension_protocol='yes',kaggle=dict(dataset_id='private/new',training_kernel_id='private/train',inference_kernel_id='private/predict'))
            pairs=pd.DataFrame([dict(comment_id='c1',post_id='v1',target_id='a',text='Actor A')])
            with patch.object(remote,'verify'),patch.object(training,'prediction_pairs',return_value=pairs),patch.object(training,'prediction_comments',return_value=pairs):
                result=remote.prepare(settings,plan,root,study,configs[2],'predict')
            self.assertEqual((result/'payload/src/polarization_pipeline/original.py').read_text(),'frozen = True\n')
            self.assertFalse((result/'payload/src/polarization_pipeline/analysis_only.py').exists())
            with tarfile.open(result/'dataset/targeted_payload.tar.gz') as tar:
                names=tar.getnames()
            self.assertFalse(any('annotations' in name or '.env' in name for name in names))
            self.assertIn('publication/prediction_input.csv',names)
