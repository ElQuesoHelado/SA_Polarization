"""Partial capture contribution and annotation workload, without valence labels."""
from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd

from ..common import atomic_json, read_csv, sha256, stamp
from ..diagnostics import EVENT_COLUMNS, opportunities
from .local_preparation import assemble, inventory, SourceChanged
from .state import verify, seal, output, lock


def run(settings, plan, study, registry):
    with lock(study / 'capture_audit.lock'):
        return audit(settings, plan, study, registry)


def audit(settings, plan, study, registry):
    verify(study)
    sources, states = inventory(study)
    union, versions, exclusions, candidates, cache = assemble(settings, study, registry, sources, write=False)
    historical_ids = set(read_csv(study / 'historical.csv', usecols=['comment_id']).comment_id)
    historical = union.loc[union.comment_id.isin(historical_ids)]
    new = union.loc[~union.comment_id.isin(historical_ids)]
    events = []
    for row, value in zip(union.itertuples(), candidates):
        for group in {m['target_group'] for m in json.loads(value)} & {'izquierda','derecha'}:
            events.append((row.user_id,row.comment_id,row.post_id,row.channel_id,row.party,row.comment_published_at[:7],group))
    events = pd.DataFrame(events, columns=EVENT_COLUMNS)
    eligible = {}
    for name, frame in [('historical',historical),('union',union)]:
        selected = events.loc[events.comment_id.isin(frame.comment_id)]
        opportunity = opportunities(selected, Counter(frame.loc[frame.user_id.ne(''),'user_id']), settings, seed=plan['seed'])
        eligible[name] = opportunity.loc[opportunity.potentially_paired].copy()
    ranked = eligible['union'].copy()
    ranked['rank_hash'] = ranked.user_id.map(lambda u:hashlib.sha256(f"ap-publication:{plan['selection_seed']}:{u}".encode()).hexdigest())
    ranked = ranked.sort_values(['rank_hash','user_id'])
    workload = [dict(candidate_users=min(n,len(ranked)), requested_prefix=n,
        comments=int(ranked.iloc[:n].total_comments.sum())) for n in (100,500,800,1000)]
    distributions = []
    for scope, frame in [('historical',historical),('new',new),('union',union)]:
        frame = frame.assign(month=frame.comment_published_at.str[:7])
        for dimension in ('party','channel_id','month','comment_type'):
            distributions.extend(dict(scope=scope,dimension=dimension,value=value,comments=int(count))
                for value,count in frame[dimension].value_counts().items())
    parents = union.set_index('comment_id').post_id
    replies = new.loc[new.parent_id.ne('')]
    parent_posts = replies.parent_id.map(parents)
    links = dict(new_replies=len(replies), parent_present=int(parent_posts.notna().sum()),
        parent_missing=int(parent_posts.isna().sum()),
        parent_other_video=int((parent_posts.notna() & parent_posts.ne(replies.post_id)).sum()))
    if any(sha256(path) != expected for _,path,expected in sources):
        raise SourceChanged('La captura cambió durante la auditoría; repetir sin publicar resultados mezclados')
    verify(study)
    destination = output(settings, study) / 'capture_audits' / stamp().replace(':','')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.building-',dir=destination.parent))
    summary = dict(partial=not (study/'freeze.json').exists(), production_enabled=False,
        capture_status=dict(Counter(status for _,status in states)), historical_comments=len(historical),
        unique_comments=len(union), new_comments=len(new), new_replies=len(replies),
        recaptured_versions=len(versions), excluded_capture_rows=len(exclusions),
        structural_candidates_historical=len(eligible['historical']), structural_candidates_union=len(ranked),
        structural_candidates_added=len(set(ranked.user_id)-set(eligible['historical'].user_id)),
        parent_links=links, workload=workload, cache=cache,
        interpretation='Structural candidates and provisional workload, not confirmed affective comparability or polarization')
    atomic_json(temp/'summary.json',summary)
    atomic_json(temp/'sources.json',{str(path.relative_to(study)):expected for _,path,expected in sources})
    pd.DataFrame(distributions).to_csv(temp/'composition.csv',index=False)
    pd.DataFrame(workload).to_csv(temp/'annotation_workload.csv',index=False)
    (temp/'report.md').write_text('# Aporte de la captura y carga de anotación\n\n'
        f"Unión: {len(union):,} comentarios únicos; nuevos: {len(new):,}; respuestas nuevas: {len(replies):,}.\n\n"
        f"Candidatos estructurales: {len(eligible['historical']):,} en el histórico y {len(ranked):,} en la unión.\n\n"
        'La carga corresponde a prefijos de candidatos, no a usuarios afectivamente confirmados. '
        'El marco puede cambiar hasta congelar la captura. Los vínculos parent_id describen hilos API; '
        'no identifican necesariamente al destinatario del comentario.\n')
    seal(temp,[p.name for p in temp.iterdir()],diagnostic_only=True)
    temp.rename(destination)
    return dict(report=str(destination),**summary)
