"""Exact affinity bounds: unread comments are possible positives for BOTH blocks."""
from __future__ import annotations

import json
from pathlib import Path

from ..annotations import validate_items
from ..assisted import annotation_digest
from ..common import atomic_json, read_csv, sha256, stamp
from ..metrics import partition_videos
from ..registry import load_registry
from .state import seal, verify_seal, verify, lock

GROUPS = ('izquierda', 'derecha')
KEYS = ('minimum_positive_videos', 'affinity_positive_share')


def enabled(study):
    path = study / 'affinity_screening'
    if not path.exists():
        return False
    verify_seal(path)
    policy = json.loads((path/'policy.json').read_text())
    if policy['freeze_sha256'] != sha256(study/'freeze.json'):
        raise ValueError('Screening pertenece a otro snapshot')
    return True


def enable(settings, study, registry):
    verify(study, frozen=True)
    path = study/'affinity_screening'
    with lock(study/'affinity_screening.lock'):
        if not enabled(study):
            path.mkdir()
            atomic_json(path/'policy.json', dict(protocol='exact-affinity-screening-v1', created_at=stamp(),
                freeze_sha256=sha256(study/'freeze.json'), registry_sha256=sha256(registry), seed=settings['seed'],
                thresholds={k:settings[k] for k in KEYS}, authorization='User approved exact affinity screening before evaluation',
                human_review_deferred=True, stopping_by_effect=False))
            seal(path, ['policy.json'])
        policy = json.loads((path/'policy.json').read_text())
        if (policy['registry_sha256'] != sha256(registry) or policy['seed'] != settings['seed']
                or policy['thresholds'] != {k:settings[k] for k in KEYS}):
            raise ValueError('Criterios del screening alterados')
    return dict(enabled=True, protocol=policy['protocol'], human_decisions_written=0)


def assess(sample, annotations, registry, settings):
    """Pure assessment. No absent annotation is represented as []."""
    if sample.sample_id.duplicated().any() or not set(annotations) <= set(sample.sample_id):
        raise ValueError('IDs de screening incompatibles')
    targets = {t['target_id']:t.get('target_group','unknown') for t in load_registry(registry, frozen=True)['targets']}
    frame = sample.copy()
    frame['fold'] = partition_videos(frame, settings['seed'])
    positive = {}
    for row in frame.itertuples():
        if row.sample_id not in annotations:
            continue
        items = validate_items(annotations[row.sample_id], row.text, set(targets))
        groups = {}
        for item in items:
            groups.setdefault(targets.get(item['target_id'],'unknown'), set()).add(item['valence'])
        # Same collapse rule as collapse_events: positive + negative or mixed is not positive.
        positive[row.sample_id] = {g for g, labels in groups.items() if g in GROUPS and 'positive' in labels
                                  and 'negative' not in labels and 'mixed' not in labels}
    users, queue, skipped = [], [], []
    for uid, history in frame.groupby('user_id', sort=False):
        a = history.loc[history.fold.eq('A')]
        unread = a.loc[~a.sample_id.isin(annotations)]
        counts = {g:0 for g in GROUPS}; videos = {g:set() for g in GROUPS}
        for row in a.itertuples():
            for g in positive.get(row.sample_id, set()):
                counts[g] += 1; videos[g].add(row.post_id)
        bounds = {}
        for g in GROUPS:
            other = GROUPS[1] if g == GROUPS[0] else GROUPS[0]
            best = counts[g] + len(unread)
            denominator = best + counts[other]
            bounds[g] = dict(maximum_positive_events=best, maximum_positive_videos=len(videos[g] | set(unread.post_id)),
                maximum_positive_share=best/denominator if denominator else 0.)
        possible = [g for g,b in bounds.items() if b['maximum_positive_events'] >= 2
            and b['maximum_positive_videos'] >= settings['minimum_positive_videos']
            and b['maximum_positive_share'] >= settings['affinity_positive_share']
            and (len(unread) or counts[g] > counts[GROUPS[1] if g == GROUPS[0] else GROUPS[0]])]
        required = []; omitted = []
        if not possible:
            status = 'excluded_affinity'
            omitted = history.loc[~history.sample_id.isin(annotations),'sample_id'].tolist()
        elif len(unread):
            status = 'waiting_affinity'
            order = a.groupby('post_id').size().rename('size').reset_index().sort_values(['size','post_id'])
            # One video at a time; recompute bounds after its import.
            vid = next(v for v in order.post_id if unread.post_id.eq(v).any())
            required = unread.loc[unread.post_id.eq(vid)].sort_values('comment_id').sample_id.tolist()
        else:
            b = history.loc[history.fold.eq('B') & ~history.sample_id.isin(annotations)].sort_values(['post_id','comment_id'])
            status = 'waiting_evaluation' if len(b) else 'complete'
            required = b.sample_id.tolist()
        queue.extend(required); skipped.extend(omitted)
        users.append(dict(user_id=uid, status=status, positive_counts=counts,
            positive_videos={g:len(v) for g,v in videos.items()}, bounds=bounds,
            required_sample_ids=required, skipped_sample_ids=omitted))
    return dict(users=users, required_sample_ids=queue, skipped_sample_ids=skipped,
        complete=not any(u['status'].startswith('waiting_') for u in users),
        annotated_comments=len(annotations), skipped_comments=len(skipped), comments=len(sample))


def annotation_map(study, name, registry, stage):
    from .annotations import checked
    folder, sample, manifest, _ = checked(study, name)
    targets = {t['target_id'] for t in load_registry(registry, frozen=True)['targets']}
    proposals = json.loads((folder/'ai_proposals.json').read_text())
    if stage == 'provisional':
        values = {sid: value['annotations'] for sid,value in proposals.items()}
    elif stage == 'final':
        form = read_csv(folder/'human_review.csv')
        if form.sample_id.duplicated().any() or set(form.sample_id) != set(sample.sample_id):
            raise ValueError('Formulario humano incompatible')
        expected = sample.set_index('sample_id'); values = {}
        for row in form.itertuples():
            if row.text != expected.loc[row.sample_id,'text']:
                raise ValueError('Texto humano alterado')
            if row.review_complete.lower() != 'true':
                continue
            items = validate_items(json.loads(row.annotation_json),row.text,targets)
            if not row.reviewer_id.strip() or not row.reviewed_at.strip():
                raise ValueError('Decisión humana sin procedencia')
            if manifest['human_mode'] != 'assisted' or row.sample_id not in proposals:
                raise ValueError('Screening requiere revisión asistida trazable')
            proposal = proposals[row.sample_id]['annotations']
            if (row.proposal_sha256 != annotation_digest(proposal)
                    or row.decision != ('accepted' if items == proposal else 'modified')):
                raise ValueError('Decisión humana sin propuesta íntegra')
            values[row.sample_id] = items
    else:
        raise ValueError('Etapa inválida')
    for row in sample.itertuples():
        if row.sample_id in values:
            validate_items(values[row.sample_id],row.text,targets)
    return folder,sample,values


def inspect(settings, study, registry, name, stage='provisional', *, persist=False):
    if not name.startswith('cohort_') or not enabled(study):
        raise ValueError('Habilitar screening para una cohorte')
    policy = json.loads((study/'affinity_screening/policy.json').read_text())
    if (policy['registry_sha256'] != sha256(registry) or policy['seed'] != settings['seed']
            or policy['thresholds'] != {k:settings[k] for k in KEYS}):
        raise ValueError('Criterios del screening alterados')
    folder,sample,values = annotation_map(study,name,registry,stage)
    ranked = read_csv(study/'eligible_users.csv').set_index('user_id')['rank'].astype(int)
    sample = sample.assign(_rank=sample.user_id.map(ranked)).sort_values('_rank').drop(columns='_rank')
    result = assess(sample,values,registry,settings)
    result.update(stage=stage,sample=name,sample_sha256=sha256(folder/'sample.csv'),
        registry_sha256=sha256(registry),policy_sha256=sha256(study/'affinity_screening/manifest.json'),
        proposal_sha256=sha256(folder/'ai_proposals.json'), human_review_sha256=sha256(folder/'human_review.csv'),
        excluded_users=sum(u['status']=='excluded_affinity' for u in result['users']), human_decisions_written=0)
    if persist:
        path=folder/'screening'/stage
        path.mkdir(parents=True,exist_ok=True)
        atomic_json(path/(stamp().replace(':','')+'.json'),result)
        atomic_json(path/'latest.json',result)
    return result,sample,values


def decisions(settings,study,name,registry,stage):
    result,sample,values=inspect(settings,study,registry,name,stage)
    if not result['complete']:
        raise ValueError('Screening incompleto; faltan anotaciones necesarias')
    # Null means genuinely unread, not no targets. Validate the certificate on EVERY read.
    return sample.assign(annotation_json=sample.sample_id.map(lambda sid:json.dumps(values[sid],ensure_ascii=False) if sid in values else None),
        annotation_status=sample.sample_id.map(lambda sid:'annotated' if sid in values else 'skipped_affinity'),
        affinity_excluded=sample.user_id.isin({u['user_id'] for u in result['users'] if u['status']=='excluded_affinity'}))


def export(settings,study,registry,name,stage='provisional',limit=50):
    if limit < 1:
        raise ValueError('limit debe ser positivo')
    result,sample,_=inspect(settings,study,registry,name,stage,persist=True)
    ids=result['required_sample_ids'][:limit]
    if not ids:
        return dict(complete=result['complete'], required_comments=0, excluded_users=result['excluded_users'])
    rows=sample.set_index('sample_id').loc[ids]
    path=study/'annotations'/name/'screening'/'queues'/(stamp().replace(':','')+'.json')
    atomic_json(path,dict(sample_sha256=result['sample_sha256'],stage=stage,origin='',proposals=[dict(sample_id=sid,
        text=row.text,user_id=row.user_id,post_id=row.post_id,annotations=None,note='',target_hints=json.loads(row.candidates_json)) for sid,row in rows.iterrows()]))
    return dict(queue=str(path),comments=len(ids),complete=False,stage=stage,excluded_users=result['excluded_users'])


def policy_settings(study):
    enabled(study)
    policy=json.loads((study/'affinity_screening/policy.json').read_text())
    return {**policy['thresholds'],'seed':policy['seed']}


def audit(settings,study,registry,names):
    """Replay only already complete references; compare eligibility and primary metrics."""
    import numpy as np
    import pandas as pd
    from .analysis import events_from_annotations,scores
    frames=[];truth={}
    for name in names:
        _,sample,values=annotation_map(study,name,registry,'provisional')
        if set(values)!=set(sample.sample_id):
            raise ValueError('Auditar solo cohortes con lectura completa')
        frames.append(sample);truth.update(values)
    sample=pd.concat(frames,ignore_index=True);known={}
    for _ in range(len(sample)+1):
        result=assess(sample,known,registry,settings)
        if result['complete']:break
        for sid in result['required_sample_ids']:known[sid]=truth[sid]
    if not result['complete']:raise ValueError('Replay sin terminar')
    def scored(values):
        frame=sample.assign(annotation_json=sample.sample_id.map(lambda sid:json.dumps(values[sid]) if sid in values else None))
        return scores(events_from_annotations(frame,registry),settings).set_index('user_id')
    full=scored(truth);fast=scored(known).reindex(full.index)
    if full.paired.tolist()!=fast.paired.eq(True).tolist():raise ValueError('Screening cambió selección')
    selected=full.index[full.paired]
    for key in ['gap','AP_In','AP_Out','AP_target','spread','in_rate','out_rate']:
        if not np.allclose(full.loc[selected,key],fast.loc[selected,key],equal_nan=True):
            raise ValueError('Screening cambió medición primaria')
    skipped=sample.loc[~sample.sample_id.isin(known)]
    report=dict(comments=len(sample),users=sample.user_id.nunique(),comparable_users=int(full.paired.sum()),
        read_comments=len(known),avoided_comments=len(skipped),avoided_fraction=len(skipped)/len(sample),
        characters_avoided_fraction=float(skipped.text.str.len().sum()/sample.text.str.len().sum()),
        selection_identical=True,primary_metrics_identical=True,source_cohorts=names,
        simulation_only=True,human_decisions_written=0,created_at=stamp())
    from .state import output
    path=output(settings,study)/'affinity_screening_audits'/(stamp().replace(':','')+'.json')
    atomic_json(path,report)
    return {**report,'report':str(path)}
