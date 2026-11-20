"""Presentation batches never change the frozen user sample or its ordering."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

from ..common import atomic_json, read_csv, sha256
from .annotations import checked
from .state import seal, verify_seal, lock

SIZE = 50


def indices(length, number):
    if isinstance(number, bool) or not isinstance(number, int) or number < 1 or (number-1)*SIZE >= length:
        raise ValueError('Número de tanda fuera de la muestra')
    return range((number-1)*SIZE, min(number*SIZE, length))


def export(study, name, number=1):
    folder, sample, manifest, _ = checked(study, name)
    selected = sample.iloc[list(indices(len(sample), number))]
    destination = folder / 'work_batches' / f'{number:04d}'
    with lock(folder / 'batch_export.lock'):
        if destination.exists():
            saved = verify_seal(destination)
            if saved['sample_sha256'] != sha256(folder / 'sample.csv'):
                raise ValueError('La tanda corresponde a otra muestra')
        else:
            destination.parent.mkdir(exist_ok=True)
            temp = Path(tempfile.mkdtemp(prefix='.building-', dir=destination.parent))
            blind = manifest['human_mode'] == 'blind'
            rows = []
            for row in selected.itertuples():
                item = dict(sample_id=row.sample_id, text=row.text)
                if not blind:
                    import json
                    item['target_hints'] = [{k:m[k] for k in ('target_id','target_name','mention_start','mention_end')}
                        for m in json.loads(row.candidates_json)]
                rows.append(item)
            atomic_json(temp / 'reading.json', rows)
            if not blind:
                atomic_json(temp / 'proposal_template.json', dict(sample_sha256=sha256(folder / 'sample.csv'),
                    origin='', proposals=[dict(sample_id=r['sample_id'], annotations=None, note='') for r in rows]))
            seal(temp, [p.name for p in temp.iterdir()], sample_sha256=sha256(folder / 'sample.csv'),
                batch_number=number, size=SIZE, human_mode=manifest['human_mode'])
            temp.rename(destination)
    form = read_csv(folder / 'human_review.csv')
    done = form.set_index('sample_id').loc[selected.sample_id].review_complete.str.lower().eq('true')
    return dict(folder=str(destination), batch_number=number, total_batches=math.ceil(len(sample)/SIZE),
        comments=len(selected), human_confirmed=int(done.sum()), human_pending=int((~done).sum()),
        human_mode=manifest['human_mode'])
