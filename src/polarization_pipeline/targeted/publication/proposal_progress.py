"""Resumable proposal progress; stopping uses comparability, never effect estimates."""
from __future__ import annotations

import json

import pandas as pd

from ..common import atomic_json, read_csv, sha256, stamp
from .annotations import checked
from .analysis import events_from_annotations, scores
from .state import verify, output


def report(settings, plan, study, registry):
    verify(study, frozen=True)
    ranked = read_csv(study / 'eligible_users.csv')
    folders = sorted((study / 'annotations').glob('cohort_[0-9][0-9][0-9][0-9]'))
    if [p.name for p in folders] != [f'cohort_{i:04d}' for i in range(1, len(folders)+1)]:
        raise ValueError('Secuencia de cohortes incompleta')
    from . import screening
    accelerated = screening.enabled(study)
    samples, complete_samples, readiness = [], [], {}
    names = (['benchmark'] if (study / 'annotations/benchmark').exists() else []) + [p.name for p in folders]
    pending_cohorts = []
    for name in names:
        folder, sample, manifest, state = checked(study, name)
        proposals = json.loads((folder / 'ai_proposals.json').read_text())
        if not set(proposals) <= set(sample.sample_id) or sample.sample_id.duplicated().any():
            raise ValueError('Identidades de propuestas incompatibles')
        complete = set(proposals) == set(sample.sample_id)
        screened_frame = None
        info = None
        if accelerated and name.startswith('cohort_'):
            info, _, _ = screening.inspect(settings,study,registry,name,'provisional')
            complete = info['complete']
            if complete:
                screened_frame = screening.decisions(settings,study,name,registry,'provisional')
        form = read_csv(folder / 'human_review.csv')
        if set(form.sample_id) != set(sample.sample_id) or form.sample_id.duplicated().any():
            raise ValueError('Formulario humano incompatible')
        readiness[name] = dict(comments=len(sample), proposals=len(proposals), proposals_complete=complete,
            human_confirmed=int(form.review_complete.str.lower().eq('true').sum()), human_mode=manifest['human_mode'],
            sample_sha256=sha256(folder / 'sample.csv'), proposals_sha256=state['sha256'])
        if info is not None:
            readiness[name].update(screening_complete=complete, skipped_comments=info['skipped_comments'],
                excluded_users=info['excluded_users'], proposals_complete=len(proposals)==len(sample))
        if name != 'benchmark':
            samples.append(sample)
            if complete:
                if pending_cohorts:
                    raise ValueError('No avanzar sobre una cohorte incompleta')
                complete_samples.append(screened_frame if screened_frame is not None else sample.assign(annotation_json=sample.sample_id.map(
                    lambda sid: json.dumps(proposals[sid]['annotations'], ensure_ascii=False))))
            else:
                pending_cohorts.append(name)
    allocated = pd.concat(samples, ignore_index=True) if samples else pd.DataFrame(columns=['user_id', 'comment_id'])
    if allocated.comment_id.duplicated().any() or set(allocated.user_id) != set(ranked.iloc[:allocated.user_id.nunique()].user_id):
        raise ValueError('Historias duplicadas o prefijo congelado alterado')
    paired = 0
    if complete_samples:
        complete_frame = pd.concat(complete_samples, ignore_index=True)
        paired = int(scores(events_from_annotations(complete_frame, registry), settings).paired.sum())
    benchmark_ready = readiness.get('benchmark', {}).get('proposals_complete', False)
    exhausted = allocated.user_id.nunique() == len(ranked) and not pending_cohorts
    from .fixed_scope import policy
    fixed=policy(study)
    if fixed and allocated.user_id.nunique()>fixed['screened_users']:
        raise ValueError('Usuarios fuera del techo fijo')
    target = ((allocated.user_id.nunique()==fixed['screened_users']) if fixed else paired >= plan['comparable_users']) and not pending_cohorts
    if not benchmark_ready:
        status = 'waiting_benchmark_proposals'
    elif pending_cohorts:
        status = 'waiting_cohort_proposals'
    elif target or exhausted:
        status = 'provisional_scope_ready'
    else:
        status = 'ready_for_next_cohort'
    result = dict(created_at=stamp(), study=study.name, stage='provisional', status=status,
        measurement_basis='ai_proposals', independently_validated=False, production_enabled=False,
        samples=readiness, allocated_users=int(allocated.user_id.nunique()), allocated_comments=len(allocated),
        fully_proposed_users=int(sum(s.annotation_json.notna().groupby(s.user_id).all().sum() for s in complete_samples)),
        screening_ready_users=int(sum(s.user_id.nunique() for s in complete_samples)),
        screening_enabled=accelerated,
        comments_skipped_by_certificate=sum(v.get('skipped_comments',0) for v in readiness.values()),
        provisional_comparable_users=paired, target_comparable_users=plan['comparable_users'],
        stopping_rule='fixed_screened_users' if fixed else 'comparable_users_or_exhaustion',
        screened_users_ceiling=fixed['screened_users'] if fixed else None,
        target_reached=target, frame_exhausted=exhausted, eligible_users=len(ranked),
        pending_cohorts=pending_cohorts, no_stopping_by_gap_or_significance=True,
        human_review_required_for_final=True)
    destination = output(settings, study) / 'proposal_progress'
    destination.mkdir(exist_ok=True)
    atomic_json(destination / (stamp().replace(':', '') + '.json'), result)
    atomic_json(destination / 'latest.json', result)
    return result
