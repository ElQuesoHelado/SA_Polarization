"""Isolated immutable benchmark prediction view; no cohort completion dependency."""
from __future__ import annotations

import json

from ..common import atomic_json, sha256
from .state import verify, verify_seal, seal, lock


def benchmark_view(study, plan, *, create=False):
    verify(study, frozen=True)
    path=study/'prediction_jobs'/(study.name+'_benchmark_v1')
    if not path.exists() and not create:
        raise FileNotFoundError('Preparar primero predict --scope benchmark')
    if create:
        with lock(study/'benchmark_prediction.lock'):
            if not path.exists():
                verify_seal(study/'training')
                path.mkdir(parents=True)
                snapshot=json.loads((study/'freeze.json').read_text())
                names=set(snapshot['files']) | {'study.json','freeze.json','training','capture_manifest.json'}
                for name in sorted(names):
                    target=path/name;target.parent.mkdir(parents=True,exist_ok=True)
                    target.symlink_to((study/name).resolve(),target_is_directory=(study/name).is_dir())
                (path/'annotations').mkdir()
                (path/'annotations/benchmark').symlink_to((study/'annotations/benchmark').resolve(),target_is_directory=True)
                atomic_json(path/'scope.json',dict(scope='benchmark',source_study=str(study.resolve()),
                    freeze_sha256=sha256(study/'freeze.json'),benchmark_sha256=sha256(study/'benchmark.csv'),
                    training_sha256=sha256(study/'training/manifest.json'),production_enabled=False))
                seal(path,['scope.json'],filename='scope_manifest.json')
    verify_seal(path,'scope_manifest.json')
    scope=json.loads((path/'scope.json').read_text())
    if (scope['source_study'] != str(study.resolve()) or scope['freeze_sha256'] != sha256(study/'freeze.json')
            or scope['benchmark_sha256'] != sha256(study/'benchmark.csv')
            or scope['training_sha256'] != sha256(study/'training/manifest.json')):
        raise ValueError('Alcance benchmark alterado')
    snapshot=json.loads((study/'freeze.json').read_text())
    for name in set(snapshot['files']) | {'study.json','freeze.json','training','capture_manifest.json'}:
        if (path/name).resolve() != (study/name).resolve():
            raise ValueError('Vista benchmark redirigida a otra entrada')
    if ((path/'annotations/benchmark').resolve() != (study/'annotations/benchmark').resolve()
            or list((path/'annotations').glob('cohort_*'))):
        raise ValueError('Vista benchmark contiene otro alcance de anotación')
    revised={**plan,'kaggle':{**plan['kaggle'],
        'inference_kernel_id':plan['kaggle']['inference_kernel_id']+'-benchmark'}}
    return path,revised
