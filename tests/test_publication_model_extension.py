"""Immutable encoder extension and five-model comparison, without services."""
import copy
import json
import shutil
import sys
import tempfile
import tomllib
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import test_publication as fixtures
from polarization_pipeline.targeted.common import atomic_json, read_csv, sha256
from polarization_pipeline.targeted.publication import annotations, benchmark, training
from polarization_pipeline.targeted.publication import remote
from polarization_pipeline.targeted.publication import model_extension as extension
from polarization_pipeline.targeted.publication.prediction_scope import benchmark_view
from polarization_pipeline.targeted.publication.state import seal, verify_seal

ROOT = Path(__file__).resolve().parents[1]


class EncoderExtensionTests(unittest.TestCase):
    def fixture(self, root):
        helper = fixtures.PublicationTests()
        settings, plan, parent, study, registry = helper.freeze_fixture(root)
        base = tomllib.loads((ROOT / 'config/targeted_publication.toml').read_text())
        plan = {**base, **plan}
        annotations.init_benchmark(study)
        helper.proposals(study, 'benchmark', registry)
        source, trained = study / 'training_input', study / 'training'
        source.mkdir(); trained.mkdir()
        for split, prefix in (('train', 'training'), ('validation', 'validation')):
            rows = [dict(comment_id=f'{split}{i}', post_id=f'{split}{i}', target_id='a', target_name='Actor A',
                         text='Actor A text', mention_start=0, mention_end=7, split=split, label=label, weight=i+1)
                    for i, label in enumerate(('positive', 'negative', 'neutral', 'mixed'))]
            frame = pd.DataFrame(rows)
            frame.to_csv(source / f'{split}.csv', index=False)
            frame.iloc[[2, 0, 1]][['comment_id', 'target_id']].to_csv(trained / f'shared_{prefix}_pairs.csv', index=False)
        atomic_json(source / 'plan.json', plan)
        seal(source, ['train.csv', 'validation.csv', 'plan.json'])
        atomic_json(trained / 'comparison.json', dict(completed_fits=12, production_enabled=False))
        seal(trained, ['shared_training_pairs.csv', 'shared_validation_pairs.csv', 'comparison.json'])
        view, _ = benchmark_view(study, plan, create=True)
        pairs = training.prediction_pairs(view, registry)
        pairs.to_csv(view / 'prediction_input.csv', index=False)
        training.prediction_comments(view)[['comment_id', 'post_id']].to_csv(view / 'prediction_scope.csv', index=False)
        self.predictions(view, pairs, benchmark.MODEL_IDS)
        config = root / 'extension.toml'
        config.write_text((ROOT / 'config/targeted_publication_models_v2.toml').read_text().replace('resolve_once', 'a'*40))
        return settings, plan, parent, study, registry, config

    def predictions(self, study, pairs, models):
        folder = study / 'predictions'; folder.mkdir()
        for model in models:
            frame = pairs[['sample_id', 'comment_id', 'post_id', 'target_id']].copy()
            frame['model_id'], frame['valence'] = model, 'positive'
            frame['accepted'], frame['context_complete'], frame['confidence'] = True, True, .99
            frame.to_csv(folder / f'{model}.csv', index=False)
        seal(folder, [f'{m}.csv' for m in models], diagnostic_only=True,
             prediction_input_sha256=sha256(study / 'prediction_input.csv'),
             prediction_scope_sha256=sha256(study / 'prediction_scope.csv'))

    def test_extension_reuses_exact_rows_weights_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, plan, parent, study, _, config = self.fixture(Path(tmp))
            before = sha256(study / 'training/manifest.json')
            folder, expanded = extension.view(settings, plan, study, 'encoder_extension_20261122_v1', config, create=True)
            prepared = training.prepare(settings, expanded, parent, folder)
            rows = read_csv(prepared / 'train.csv')
            self.assertEqual(rows.comment_id.tolist(), ['train2', 'train0', 'train1'])
            self.assertEqual(rows.weight.astype(int).tolist(), [3, 1, 2])
            self.assertEqual(set(rows.split), {'train'})
            self.assertEqual(json.loads((prepared / 'plan.json').read_text())['maximum_fits'], 6)
            self.assertEqual(extension.view(settings, plan, study, folder.name)[0], folder)
            self.assertEqual(training.prepare(settings, expanded, parent, folder), prepared)
            self.assertEqual(sha256(study / 'training/manifest.json'), before)
            self.assertFalse((parent / 'model/test_opened.json').exists())

    def test_extension_rejects_changed_baseline_or_changed_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, plan, _, study, _, config = self.fixture(Path(tmp))
            folder, _ = extension.view(settings, plan, study, 'encoder_extension_20261122_v1', config, create=True)
            config.write_text(config.read_text().replace('maximum_fits = 6', 'maximum_fits = 9'))
            with self.assertRaisesRegex(ValueError, 'Configuración distinta'):
                extension.view(settings, plan, study, folder.name, config)
            (study / 'training/shared_training_pairs.csv').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'referencia'):
                extension.verify_extension(folder)

    def test_extension_validates_budget_and_preserves_original_protocol(self):
        original = tomllib.loads((ROOT / 'config/targeted_publication.toml').read_text())
        training.validate_plan(original)
        specification = tomllib.loads((ROOT / 'config/targeted_publication_models_v2.toml').read_text())
        expanded = {**original, **specification, 'model_extension_protocol': extension.PROTOCOL}
        training.validate_plan(expanded)
        for key, value in (('maximum_fits', 12), ('reference_models', ['beto']), ('model_seeds', [42])):
            changed = {**expanded, key: value}
            with self.assertRaises(ValueError):
                training.validate_plan(changed)
        with self.assertRaises(ValueError):
            training.validate_plan({**original, 'models': specification['models']})

    def test_worker_completes_only_six_fits_and_never_repeats_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, plan, parent, study, _, config = self.fixture(Path(tmp))
            folder, expanded = extension.view(settings, plan, study, 'encoder_extension_20261122_v1', config, create=True)
            training.prepare(settings, expanded, parent, folder)
            module = types.ModuleType('transformers')
            module.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **k: types.SimpleNamespace(model_max_length=512))
            module.AutoConfig = types.SimpleNamespace(from_pretrained=lambda *a, **k: types.SimpleNamespace(max_position_embeddings=512, model_type='modernbert'))
            seen = []
            def fit(setting, train, val, destination, spec, trial, recipe, seed):
                self.assertEqual(train.comment_id.tolist(), ['train2', 'train0', 'train1'])
                checkpoint = destination / str(seed); checkpoint.mkdir()
                (checkpoint / 'weights').write_text('synthetic only')
                logits = np.eye(5)[[2, 0, 1]] * 5
                np.save(destination / f'validation_logits_{seed}.npy', logits)
                seen.append((spec['id'], seed))
                return dict(seed=seed), logits
            with patch.dict(sys.modules, {'transformers': module}), \
                 patch.object(training, 'complete_context', side_effect=lambda t, f, m: np.ones(len(f), dtype=bool)), \
                 patch.object(training, 'fit_seed', side_effect=fit):
                training.train_worker(dict(quality=dict(valence_precision=.85)), folder)
                training.train_worker(dict(quality=dict(valence_precision=.85)), folder)
            self.assertEqual(len(seen), 6)
            self.assertEqual({m for m, _ in seen}, set(extension.NEW_MODELS))
            self.assertEqual(json.loads((folder / 'training/comparison.json').read_text())['completed_fits'], 6)

    def test_worker_rejects_silent_context_exclusions_before_fitting(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, plan, parent, study, _, config = self.fixture(Path(tmp))
            folder, expanded = extension.view(settings, plan, study, 'encoder_extension_20261122_v1', config, create=True)
            training.prepare(settings, expanded, parent, folder)
            module = types.ModuleType('transformers')
            module.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **k: types.SimpleNamespace(model_max_length=512))
            module.AutoConfig = types.SimpleNamespace(from_pretrained=lambda *a, **k: types.SimpleNamespace(max_position_embeddings=512, model_type='modernbert'))
            with patch.dict(sys.modules, {'transformers': module}), \
                 patch.object(training, 'complete_context', side_effect=lambda t, f, m: np.array([True, False, True])), \
                 patch.object(training, 'fit_seed') as fit:
                with self.assertRaisesRegex(ValueError, 'todos los pares'):
                    training.train_worker({}, folder)
                fit.assert_not_called()

    def test_five_model_benchmark_reuses_references_and_ten_contrasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, plan, parent, study, registry, config = self.fixture(Path(tmp))
            folder, expanded = extension.view(settings, plan, study, 'encoder_extension_20261122_v1', config, create=True)
            training.prepare(settings, expanded, parent, folder)
            reference = study / 'prediction_jobs' / (study.name + '_benchmark_v1')
            for name in ('prediction_input.csv', 'prediction_scope.csv'):
                shutil.copy2(reference / name, folder / name)
            pairs = read_csv(folder / 'prediction_input.csv')
            self.predictions(folder, pairs, extension.NEW_MODELS)
            # One new model cannot see the first input: recompute the panel for all five.
            changed = read_csv(folder / 'predictions/mrbert_es.csv')
            changed.loc[0, ['context_complete', 'accepted']] = 'False'
            changed.to_csv(folder / 'predictions/mrbert_es.csv', index=False)
            seal(folder / 'predictions', [f'{m}.csv' for m in extension.NEW_MODELS], diagnostic_only=True,
                 prediction_input_sha256=sha256(folder / 'prediction_input.csv'),
                 prediction_scope_sha256=sha256(folder / 'prediction_scope.csv'))
            (folder / 'training').mkdir()
            seal(folder / 'training', [])
            combined, combined_plan = extension.combine_predictions(folder)
            for name in extension.REFERENCES:
                self.assertEqual(sha256(combined / 'predictions' / f'{name}.csv'), sha256(reference / 'predictions' / f'{name}.csv'))
            self.assertFalse((combined / 'predictions/bertin.csv').exists())
            report = benchmark.compare(settings, combined_plan, combined, registry)
            self.assertEqual(len(read_csv(report / 'model_contrasts.csv')), 10)
            compared = read_csv(report / 'comparison.csv')
            common = compared.loc[compared.panel.eq('common_complete_candidates')]
            self.assertEqual(set(common.pairs.astype(int)), {len(pairs)-1})
            summary = json.loads((report / 'summary.json').read_text())
            self.assertEqual(summary['evaluated_models'], list(extension.MODEL_IDS))
            self.assertTrue(summary['benchmark_previously_examined'])
            self.assertFalse(summary['independently_validated'])
            self.assertIn('model_experiments', str(report))
            with self.assertRaises(FileExistsError):
                benchmark.compare(settings, combined_plan, combined, registry)

    def test_training_payload_contains_only_development_and_new_models(self):
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            settings, plan, parent, study, registry, config = self.fixture(Path(tmp))
            settings['kaggle'] = dict(dataset_id='old/data', training_kernel_id='old/train', inference_kernel_id='old/infer')
            settings['source']['kaggle'] = dict(dataset_id='legacy/data', kernel_id='legacy/kernel')
            shutil.copytree(ROOT / 'src/polarization_pipeline', Path(tmp) / 'src/polarization_pipeline',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            folder, expanded = extension.view(settings, plan, study, 'encoder_extension_20261122_v1', config, create=True)
            stage = remote.prepare(settings, expanded, parent, folder, registry, 'train')
            with tarfile.open(stage / 'dataset/targeted_payload.tar.gz') as archive:
                names = [n for n in archive.getnames() if not n.startswith('src/')]
                self.assertFalse(any('annotations/' in n or 'benchmark.csv' in n or n.endswith('.env') for n in names))
                prepared = json.load(archive.extractfile('publication/training_input/plan.json'))
                self.assertEqual(prepared['maximum_fits'], 6)
                self.assertFalse(prepared['reserved_test_exported'])
                self.assertEqual([m['id'] for m in prepared['models']], list(extension.NEW_MODELS))
            metadata = json.loads((stage / 'kernel/kernel-metadata.json').read_text())
            self.assertTrue(metadata['is_private'])
            self.assertTrue(metadata['enable_internet'])

    def test_experiment_identifier_cannot_escape_workspace(self):
        with self.assertRaisesRegex(ValueError, 'experiment-id'):
            extension.view({}, {}, Path('/unused'), '../escape')
