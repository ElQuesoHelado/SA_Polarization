"""Sealed resource-based user ceiling, independent of effect-based stopping."""
from __future__ import annotations

import json

from ..common import atomic_json, read_csv, sha256, stamp
from .state import lock, seal, verify, verify_seal


def policy(study):
    folder = study / 'fixed_user_scope'
    if not folder.exists():
        return None
    verify_seal(folder)
    value = json.loads((folder/'policy.json').read_text())
    if value['freeze_sha256'] != sha256(study/'freeze.json'):
        raise ValueError('Alcance fijo pertenece a otro snapshot')
    return value


def enable(study, screened_users=300, initial_report_users=200):
    verify(study, frozen=True)
    if (isinstance(screened_users,bool) or isinstance(initial_report_users,bool)
            or not 0 < initial_report_users <= screened_users):
        raise ValueError('Tamaños de alcance inválidos')
    folder = study/'fixed_user_scope'
    with lock(study/'fixed_user_scope.lock'):
        previous=policy(study)
        if previous:
            if (previous['screened_users'],previous['initial_report_users']) != (screened_users,initial_report_users):
                raise ValueError('Alcance fijo ya sellado; no cambiar después de analizar')
            return previous
        allocated=set()
        sources={}
        for path in sorted((study/'annotations').glob('cohort_*/sample.csv')):
            allocated.update(read_csv(path).user_id)
            sources[str(path.relative_to(study))]=sha256(path)
        if len(allocated)>screened_users:
            raise ValueError('Ya hay usuarios seleccionados fuera del techo solicitado')
        if screened_users>len(read_csv(study/'eligible_users.csv')):
            raise ValueError('Techo superior al marco')
        folder.mkdir()
        value=dict(protocol='fixed-screened-users-v1',created_at=stamp(),screened_users=screened_users,
            initial_report_users=initial_report_users,freeze_sha256=sha256(study/'freeze.json'),
            authorization=f'User approved immediate report at {initial_report_users} and resource-limited completion at {screened_users}',
            reason='Assistant usage budget; no stopping by affect, precision or significance',
            selected_samples=sources,original_comparable_target=800,include_all_comparables=True,
            human_review_required_for_final=True)
        atomic_json(folder/'policy.json',value)
        seal(folder,['policy.json'])
        return value
