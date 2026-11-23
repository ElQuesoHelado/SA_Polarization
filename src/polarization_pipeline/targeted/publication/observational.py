"""Additive observational diagnostics. No annotation, threshold or model promotion."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from ..common import atomic_json, read_csv, sha256, stamp
from ..metrics import partition_videos
from ..registry import load_registry
from .state import seal, verify, verify_seal, lock

PROTOCOL = 'targeted-publication-observational-diagnostics-v1'
GROUPS = ('izquierda', 'derecha')
VALID = ('positive', 'negative', 'neutral')


class EventScores:
    """Vectorized equivalent of the fixed scoring rule, with explicit diagnostic variants."""
    def __init__(self, events, users, channels):
        self.users=np.asarray(users); self.channels=np.asarray(channels)
        self.events=events.loc[events.valence.isin(VALID)].copy()
        e=self.events
        self.u=e.user_id.map(dict(zip(users,range(len(users))))).to_numpy(dtype=int)
        self.g=e.target_group.map(dict(izquierda=0,derecha=1)).to_numpy(dtype=int)
        self.c=e.channel_id.map(dict(zip(channels,range(len(channels))))).to_numpy(dtype=int)
        self.v,video_names=pd.factorize(e.post_id,sort=False);self.nvideos=len(video_names)
        self.fold=partition_videos(e,42).eq('B').to_numpy()
        self.sign=e.valence.map(dict(positive=1.,negative=-1.,neutral=0.)).to_numpy()
        self.ug=self.u*2+self.g;self.n=len(users)
        self.unique_positive={}
        for fold in (False,True):
            idx=np.flatnonzero((self.fold==fold)&(self.sign==1))
            _,first=np.unique(self.ug[idx]*max(1,self.nvideos)+self.v[idx],return_index=True)
            self.unique_positive[fold]=idx[first]

    def score(self, channel_weights=None, *, reverse=False, min_positive=2, share=2/3,
              min_events=3, min_videos=2, min_per_block=1, balanced=False,
              neutral_denominator=True, source=None, evaluation_mask=None,
              evaluation_A=False):
        n=self.n; size=2*n
        cw=np.ones(len(self.channels)) if channel_weights is None else np.asarray(channel_weights)
        w=cw[self.c].astype(float);active=w>0
        assignment_fold=True if reverse else False
        pos=active&(self.fold==assignment_fold)&(self.sign==1)
        counts=np.bincount(self.ug[pos],weights=w[pos],minlength=size).reshape(n,2)
        ix=self.unique_positive[assignment_fold];ix=ix[active[ix]]
        pv=np.bincount(self.ug[ix],minlength=size).reshape(n,2)
        maximum=counts.max(axis=1);group=counts.argmax(axis=1)
        share_values=np.divide(maximum,counts.sum(axis=1),out=np.zeros(n),where=counts.sum(axis=1)>0)
        determined=(np.sum(counts==maximum[:,None],axis=1)==1)&(maximum>=min_positive)&(share_values>=share)&(pv[np.arange(n),group]>=2)
        # Historical adapter reports right/left counts for undetermined users;
        # those counts never become an assigned affinity or a primary score.
        group=np.where(determined,group,1)
        ev=active&(self.fold==(assignment_fold if evaluation_A else not assignment_fold))
        if source is not None:ev &= self.events.party.eq(source).to_numpy()
        if evaluation_mask is not None:ev &= np.asarray(evaluation_mask)
        weights=w.copy()
        if balanced:
            sizes=np.bincount(self.v[ev],minlength=self.nvideos)
            weights[ev]/=sizes[self.v[ev]]
        total=np.bincount(self.ug[ev],weights=weights[ev],minlength=size).reshape(n,2).astype(float)
        balances=np.bincount(self.ug[ev],weights=weights[ev]*self.sign[ev],minlength=size).reshape(n,2).astype(float)
        raw_events=np.bincount(self.u[ev],minlength=n)
        key=self.u[ev]*max(1,self.nvideos)+self.v[ev]
        unique=np.unique(key)//max(1,self.nvideos)
        videos=np.bincount(unique,minlength=n)
        metric_total=total
        if not neutral_denominator:
            nz=ev&(self.sign!=0)
            metric_total=np.bincount(self.ug[nz],weights=weights[nz],minlength=size).reshape(n,2)
        chosen=np.arange(n),group;other=np.arange(n),1-group
        n_in,n_out=metric_total[chosen],metric_total[other]
        ap_in,ap_out=balances[chosen],balances[other]
        support=(total.min(axis=1)>=min_per_block) if min_per_block>1 else np.ones(n,dtype=bool)
        paired=determined&(n_in>0)&(n_out>0)&(raw_events>=min_events)&(videos>=min_videos)&support
        rates=np.divide(balances,metric_total,out=np.full_like(balances,np.nan),where=metric_total>0)
        in_rate=rates[chosen];out_rate=rates[other]
        valid_ap=determined&(total.sum(axis=1)>0)
        return pd.DataFrame(dict(user_id=self.users,ingroup=np.where(determined,np.array(GROUPS)[group],'Undetermined'),
            paired=paired,N_in=n_in,N_out=n_out,evaluation_interactions=raw_events,evaluation_videos=videos,
            AP_In=np.where(valid_ap,ap_in,np.nan),AP_Out=np.where(valid_ap,ap_out,np.nan),
            AP_target=np.where(valid_ap,ap_in-ap_out,np.nan),
            spread=np.where(determined,np.sqrt(np.divide((balances**2).sum(axis=1),total.sum(axis=1),out=np.full(n,np.nan),where=total.sum(axis=1)>0)),np.nan),
            in_rate=np.where(paired,in_rate,np.nan),out_rate=np.where(paired,out_rate,np.nan),
            gap=np.where(paired,in_rate-out_rate,np.nan),left_rate=np.where(paired,rates[:,0],np.nan),
            right_rate=np.where(paired,rates[:,1],np.nan)))


def weighted_average(values, weights):
    values=np.asarray(values,dtype=float);weights=np.asarray(weights,dtype=float)
    valid=np.isfinite(values)&(weights>0)
    return float(np.average(values[valid],weights=weights[valid])) if valid.any() else np.nan


def trimmed(values, fraction=.1):
    x=np.sort(np.asarray(values,dtype=float));x=x[np.isfinite(x)]
    cut=int(len(x)*fraction)
    return float(x[cut:len(x)-cut].mean()) if len(x) else np.nan


def endpoints(frame, weights):
    w=np.asarray(weights,dtype=int)*frame.paired.to_numpy()
    valid=w>0;gap=frame.gap.to_numpy(dtype=float)
    repeated=np.repeat(gap[valid],w[valid])
    out={name:weighted_average(frame[name],w) for name in ('gap','in_rate','out_rate')}
    out.update(positive_share=weighted_average(gap>0,w),
        joint_share=weighted_average(frame.in_rate.gt(0)&frame.out_rate.lt(0),w),
        gap_median=float(np.median(repeated)) if len(repeated) else np.nan,
        gap_trimmed=trimmed(repeated))
    for group in GROUPS:
        gw=w*frame.ingroup.eq(group).to_numpy()
        out['gap_'+group]=weighted_average(gap,gw)
        for target,name in zip(GROUPS,('left_rate','right_rate')):
            out['balance_'+group+'_'+target]=weighted_average(frame[name],gw)
    out['difference_right_left']=out['gap_derecha']-out['gap_izquierda']
    return out


def interval(values, minimum):
    x=np.asarray(values,dtype=float);x=x[np.isfinite(x)]
    if len(x)<minimum:return np.nan,np.nan,len(x),'insufficient_support'
    low,high=np.quantile(x,[.025,.975])
    return float(low),float(high),len(x),'estimated'


def robust_statistics(frame):
    rows=[]
    for group,part in [('all',frame),*list(frame.groupby('ingroup'))]:
        for metric in ('AP_In','AP_Out','AP_target','spread','gap','N_in','N_out','evaluation_interactions','evaluation_videos'):
            x=part[metric].astype(float).dropna()
            rows.append(dict(group=group,metric=metric,users=len(x),mean=x.mean(),median=x.median(),sd=x.std(ddof=1),
                             q25=x.quantile(.25),q75=x.quantile(.75),minimum=x.min(),maximum=x.max(),trimmed10=trimmed(x)))
    return pd.DataFrame(rows)


def adverse_curve(scorer, primary, budgets):
    """Exact worst-case value at k changed B block-events, affinity and denominators fixed."""
    p=primary.set_index('user_id');e=scorer.events.copy()
    e=e.loc[e.user_id.isin(p.index)&partition_videos(e,42).eq('B')].copy()
    same=e.target_group.eq(e.user_id.map(p.ingroup))
    sign=e.valence.map(dict(positive=1.,negative=-1.,neutral=0.))
    n=np.where(same,e.user_id.map(p.N_in),e.user_id.map(p.N_out))
    # A changed ingroup event can become negative; an outgroup event positive.
    effect=np.where(same,sign+1,1-sign)/n/len(p)
    effects=np.sort(effect)[::-1];cumulative=np.cumsum(effects)
    original=primary.gap.mean();rows=[]
    for budget in budgets:
        k=int(np.floor(budget*len(e)))
        decrease=float(cumulative[k-1]) if k else 0.
        rows.append(dict(budget=budget,changed_events=k,total_B_events=len(e),users=len(p),
                         original_gap=original,worst_case_gap=original-decrease,affinity_fixed=True,denominators_fixed=True))
    crossing=np.flatnonzero(cumulative>=original)
    tip=int(crossing[0]+1) if len(crossing) else None
    return pd.DataFrame(rows),dict(minimum_event_changes_for_nonpositive_gap=tip,
        B_events=len(e),fraction=tip/len(e) if tip is not None else None,
        unit='comment_block_event',scope='B valence only; affinity, eligibility, targets and denominators fixed')


def validate_config(config, analysis_id):
    expected = dict(bootstrap_iterations=2000, split_iterations=200, screened_users=300,
        seed=42, split_seed=57, minimum_valid_fraction=.8, trim_fraction=.1,
        evaluation_event_grid=[2,3,5], affinity_share_grid=[2/3,.75],
        affinity_positive_grid=[2,3], block_support_grid=[1,2,3,5],
        adverse_error_budgets=[0.,.05,.1,.2])
    if (config.get('protocol') != PROTOCOL or config.get('analysis_id') != analysis_id or
            not re.fullmatch(r'[A-Za-z0-9_-]+', analysis_id)):
        raise ValueError('Identidad/protocolo de diagnóstico incompatible')
    if any(config.get(k) != value for k,value in expected.items()):
        raise ValueError('Especificación de diagnóstico distinta de la familia aprobada')


def verify_inputs(study, hashes, config_path, base, registry):
    special = dict(config=config_path, primary_manifest=base/'manifest.json',
                   freeze=study/'freeze.json', registry=registry)
    for name,digest in hashes.items():
        if sha256(special.get(name, study/name)) != digest:
            raise ValueError('Entrada del diagnóstico alterada: '+name)


def run(settings, study_plan, study, registry, analysis_id, *, stage='provisional', config_path=None):
    from .annotations import cohort_samples
    from .analysis import events_from_annotations
    if stage != 'provisional':
        raise ValueError('El diagnóstico final requiere otra identidad y análisis humano cerrado')
    verify(study,frozen=True)
    config_path=Path(config_path or settings['_root']/'config/targeted_observational.toml')
    config=tomllib.loads(config_path.read_text())
    validate_config(config, analysis_id)
    base=settings['outputs']/study.name/'analysis_provisional_users_0300'
    verify_seal(base)
    destination=settings['outputs']/study.name/'observational'/analysis_id
    destination.parent.mkdir(parents=True,exist_ok=True)
    with lock(destination.parent/(analysis_id+'.lock')):
        if destination.exists():
            verify_seal(destination)
            if json.loads((destination/'summary.json').read_text())['stage']!=stage:
                raise ValueError('No sobrescribir una etapa con otra')
            verify_inputs(study, json.loads((destination/'inputs.json').read_text()), config_path, base, registry)
            return destination
        pending=destination.with_name(destination.name+'.pending')
        pending.mkdir(exist_ok=False)
        sample=cohort_samples(study,registry,stage,screened_users=300)
        events=events_from_annotations(sample,registry)
        screened=pd.read_csv(base/'screened_user_scores.csv');primary=pd.read_csv(base/'primary_user_scores.csv')
        users=screened.user_id.to_numpy();channels=events.channel_id.unique()
        included=set(primary.user_id);primary_mask=np.isin(users,list(included))
        scorer=EventScores(events,users,channels);point=scorer.score()
        primary_point=point.loc[primary_mask&point.paired].copy()
        # Do not silently reuse the provisional selection if final corrections change it.
        original=primary.set_index('user_id').sort_index()
        check=primary_point.set_index('user_id').sort_index()
        if set(check.index)!=set(original.index) or not np.allclose(check[['gap','AP_In','AP_Out','spread']],original[['gap','AP_In','AP_Out','spread']],atol=1e-12):
            raise ValueError('El diagnóstico no reproduce las métricas principales')
        source_hashes={'config':sha256(config_path),'primary_manifest':sha256(base/'manifest.json'),
                       'freeze':sha256(study/'freeze.json'),'registry':sha256(registry)}
        for folder in sorted((study/'annotations').glob('cohort_*')):
            for name in ('sample.csv','ai_proposals.json','proposal_state.json','human_review.csv'):
                source_hashes[str((folder/name).relative_to(study))]=sha256(folder/name)
        atomic_json(pending/'inputs.json',source_hashes)
        robust_statistics(primary_point).to_csv(pending/'robust_statistics.csv',index=False)
        primary_point.to_csv(pending/'user_scores.csv',index=False)
        # Funnel: exclusive hierarchy and a separate overlapping-conditions table.
        reasons=[];overlap=[]
        for row in screened.itertuples():
            values=json.loads(row.exclusion_reasons)
            if row.paired:reason='comparable'
            else:
                order=('affinity_exclusion_certified','no_known_evaluable_events','affinity_undetermined',
                       'no_evaluation_ingroup','no_evaluation_outgroup','insufficient_evaluation_events','insufficient_evaluation_videos')
                reason=next((x for x in order if x in values),'other')
            reasons.append(dict(user_id=row.user_id,reason=reason))
            overlap.extend(dict(reason=x,user_id=row.user_id) for x in values)
        reasons=pd.DataFrame(reasons)
        reasons.groupby('reason').size().rename('users').to_csv(pending/'exclusion_funnel.csv')
        pd.DataFrame(overlap).groupby('reason').size().rename('users').to_csv(pending/'exclusion_overlap.csv')
        features=sample.groupby('user_id').agg(comments=('comment_id','size'),videos=('post_id','nunique'),
             channels=('channel_id','nunique'),source_groups=('party','nunique'))
        features['comparable']=features.index.isin(included)
        rows=[]
        for column in ('comments','videos','channels','source_groups'):
            yes=features.loc[features.comparable,column];no=features.loc[~features.comparable,column]
            pooled=np.sqrt((yes.var(ddof=1)+no.var(ddof=1))/2)
            for label,values in [('included',yes),('excluded',no)]:
                rows.append(dict(variable=column,group=label,users=len(values),mean=values.mean(),median=values.median(),
                    q25=values.quantile(.25),q75=values.quantile(.75),sd=values.std(ddof=1),
                    standardized_difference=(yes.mean()-no.mean())/pooled if pooled>0 else np.nan))
        pd.DataFrame(rows).to_csv(pending/'selection_observables.csv',index=False)
        features.to_csv(pending/'user_observables.csv')
        skipped=sample.loc[sample.annotation_json.isna()]
        atomic_json(pending/'reading_scope.json',dict(skipped_comments=len(skipped),users_with_unread=skipped.user_id.nunique(),
            omitted_is_not_empty_annotation=True))
        composition=events.loc[events.user_id.isin(included)].merge(primary[['user_id','ingroup']],on='user_id',validate='many_to_one')
        composition['fold']=partition_videos(composition,42)
        composition.groupby(['fold','ingroup','target_group','valence']).size().rename('events').to_csv(pending/'event_composition.csv')
        support=[]
        for k in (1,2,3,5,10):
            mask=primary_point.N_in.ge(k)&primary_point.N_out.ge(k)
            support.append(dict(minimum_per_block=k,users=int(mask.sum()),gap=primary_point.loc[mask,'gap'].mean()))
        pd.DataFrame(support).to_csv(pending/'support_thresholds.csv',index=False)
        # Fixed family of sensitivity analyses. None changes the primary definition.
        variants=[]
        def add(name,engine=None,mask=None,**kwargs):
            variants.append(dict(name=name,engine=engine or scorer,mask=primary_mask if mask is None else mask,kwargs=kwargs))
        add('reverse_A_B',reverse=True);add('balanced_video',balanced=True)
        target_groups={t['target_id']:t.get('target_group','unknown') for t in load_registry(registry,frozen=True)['targets']}
        counts={}
        for value in sample.annotation_json.dropna():
            for item in json.loads(value):
                if target_groups.get(item['target_id']) in GROUPS:counts[item['target_id']]=counts.get(item['target_id'],0)+1
        for target in sorted(counts,key=lambda k:(-counts[k],k))[:3]:
            altered=sample.copy();altered['annotation_json']=altered.annotation_json.map(
                lambda v: json.dumps([i for i in json.loads(v) if i['target_id']!=target]) if pd.notna(v) else None)
            add('exclude_'+target,EventScores(events_from_annotations(altered,registry),users,channels))
        add('historical_main_only',EventScores(events_from_annotations(sample.loc[sample.component.eq('historical_main')],registry),users,channels))
        for minimum,share,positive in itertools.product(config['evaluation_event_grid'],config['affinity_share_grid'],config['affinity_positive_grid']):
            name=f'grid_events{minimum}_share{share:.6f}_positive{positive}'
            add(name,mask=np.ones(len(users),dtype=bool),min_events=minimum,share=share,min_positive=positive)
        for minimum in config['block_support_grid']:add('support_'+str(minimum),min_per_block=minimum)
        add('without_neutral_denominator',neutral_denominator=False)
        for source in ('izquierda','derecha','neutral'):add('source_'+source,source=source)
        old_sens=pd.read_csv(base/'sensitivities.csv').set_index('variant')
        for item in variants:
            result=item['engine'].score(**item['kwargs']);mask=item['mask']&result.paired.to_numpy()
            item['point']=result;item['users']=int(mask.sum());item['estimate']=result.loc[mask,'gap'].mean()
            common=mask&point.paired.to_numpy()
            item['baseline_matched']=point.loc[common,'gap'].mean()
            item['delta_matched']=(result.loc[common,'gap']-point.loc[common,'gap']).mean()
            if item['name'] in old_sens.index:
                row=old_sens.loc[item['name']]
                if item['users']!=int(row.comparable) or not np.isclose(item['estimate'],float(row.gap),atol=1e-12):
                    raise ValueError('Sensibilidad histórica no reproducida: '+item['name'])
        # Paired A/B comparison, same original A affinity and same available users.
        apoint=scorer.score(evaluation_A=True,min_events=2,min_videos=1)
        matched=primary_mask&apoint.paired.to_numpy()&point.paired.to_numpy()
        ab_point=dict(users=int(matched.sum()),A=apoint.loc[matched,'gap'].mean(),B=point.loc[matched,'gap'].mean(),
                      difference_A_minus_B=(apoint.loc[matched,'gap']-point.loc[matched,'gap']).mean())
        # Use the primary conditional user/channel design for the primary and fixed-122 variants.
        # Grid variants use all 300, because relaxing B can admit previously ineligible users.
        channel_map=dict(zip(channels,range(len(channels))))
        def channel_strata(frame):
            return [g.channel_id.map(channel_map).to_numpy(dtype=int) for _,g in frame[['channel_id','party']].drop_duplicates().groupby('party')]
        strata_primary=channel_strata(events.loc[events.user_id.isin(included)])
        strata_all=channel_strata(events)
        user_map=dict(zip(users,range(len(users))))
        primary_indices=np.array([user_map[x] for x in events.loc[events.user_id.isin(included),'user_id'].unique()])
        rng=np.random.default_rng(config['seed']);rng_grid=np.random.default_rng(config['seed']+1)
        endpoint_draws={name:[] for name in endpoints(point,primary_mask.astype(int))}
        variant_draws={v['name']:[] for v in variants};delta_draws={v['name']:[] for v in variants}
        ab_draws=[]
        for iteration in range(config['bootstrap_iterations']):
            cw=np.zeros(len(channels))
            for indices in strata_primary:cw[indices]=rng.multinomial(len(indices),np.full(len(indices),1/len(indices)))
            uw=np.zeros(len(users),dtype=int);uw[primary_indices]=rng.multinomial(len(primary_indices),np.full(len(primary_indices),1/len(primary_indices)))
            bscore=scorer.score(cw)
            for name,value in endpoints(bscore,uw).items():endpoint_draws[name].append(value)
            all_cw=np.zeros(len(channels))
            for indices in strata_all:all_cw[indices]=rng_grid.multinomial(len(indices),np.full(len(indices),1/len(indices)))
            all_uw=rng_grid.multinomial(len(users),np.full(len(users),1/len(users)))
            grid_baseline=None
            for item in variants:
                is_grid=item['name'].startswith('grid_');weights=all_uw if is_grid else uw
                result=item['engine'].score(all_cw if is_grid else cw,**item['kwargs'])
                weights=weights*item['mask']*result.paired.to_numpy()
                variant_draws[item['name']].append(weighted_average(result.gap,weights))
                if is_grid and grid_baseline is None:grid_baseline=scorer.score(all_cw)
                baseline=grid_baseline if is_grid else bscore
                common=weights*baseline.paired.to_numpy()
                delta_draws[item['name']].append(weighted_average(result.gap-baseline.gap,common))
            ascore=scorer.score(cw,evaluation_A=True,min_events=2,min_videos=1)
            w=uw*ascore.paired.to_numpy()*bscore.paired.to_numpy()
            ab_draws.append(weighted_average(ascore.gap-bscore.gap,w))
            if (iteration+1)%100==0:print(f'Observacional: {iteration+1}/{config["bootstrap_iterations"]} remuestreos',flush=True)
        minimum=math.ceil(config['bootstrap_iterations']*config['minimum_valid_fraction'])
        rows=[]
        for name,value in endpoints(point,primary_mask.astype(int)).items():
            lo,hi,valid,status=interval(endpoint_draws[name],minimum)
            rows.append(dict(metric=name,estimate=value,ci_low=lo,ci_high=hi,valid_replicates=valid,status=status))
        pd.DataFrame(rows).to_csv(pending/'intervals.csv',index=False)
        rows=[]
        for item in variants:
            lo,hi,valid,status=interval(variant_draws[item['name']],minimum)
            dl,dh,dv,ds=interval(delta_draws[item['name']],minimum)
            rows.append(dict(variant=item['name'],users=item['users'],gap=item['estimate'],ci_low=lo,ci_high=hi,
                valid_replicates=valid,status=status,baseline_same_users=item['baseline_matched'],
                difference_same_users=item['delta_matched'],difference_ci_low=dl,difference_ci_high=dh,
                difference_status=ds,population='screened_300' if item['name'].startswith('grid_') else 'original_comparables'))
        pd.DataFrame(rows).to_csv(pending/'sensitivities.csv',index=False)
        lo,hi,valid,status=interval(ab_draws,minimum)
        atomic_json(pending/'AB_comparison.json',{**ab_point,'ci_low':lo,'ci_high':hi,'valid_replicates':valid,'status':status})
        # Repeated video-level halves of B, with A affinity retained. Variation is not a CI.
        splits=[]
        for iteration in range(config['split_iterations']):
            half=scorer.events.post_id.map(lambda v:int(hashlib.sha256(f'B-reliability:{config["split_seed"]}:{iteration}:{v}'.encode()).hexdigest()[:12],16)%2).to_numpy()
            first=scorer.score(evaluation_mask=half==0,min_events=2,min_videos=1)
            second=scorer.score(evaluation_mask=half==1,min_events=2,min_videos=1)
            valid=primary_mask&first.paired.to_numpy()&second.paired.to_numpy()
            x=first.loc[valid,'gap'];y=second.loc[valid,'gap']
            pearson=x.corr(y) if len(x)>2 and x.std()>0 and y.std()>0 else np.nan
            spearman=x.rank().corr(y.rank()) if len(x)>2 and x.std()>0 and y.std()>0 else np.nan
            splits.append(dict(split=iteration,users=int(valid.sum()),pearson=pearson,spearman=spearman))
        pd.DataFrame(splits).to_csv(pending/'split_half.csv',index=False)
        influence=[]
        for row in primary_point.itertuples():
            rest=primary_point.loc[primary_point.user_id.ne(row.user_id)]
            influence.append(dict(user_id=row.user_id,ingroup=row.ingroup,removed_AP_In=row.AP_In,
                                  removed_gap=row.gap,gap_without=rest.gap.mean()))
        pd.DataFrame(influence).to_csv(pending/'influence.csv',index=False)
        adverse,tipping=adverse_curve(scorer,primary_point,config['adverse_error_budgets'])
        adverse.to_csv(pending/'adverse_error.csv',index=False);atomic_json(pending/'adverse_tipping.json',tipping)
        summary=dict(protocol=PROTOCOL,analysis_id=analysis_id,stage=stage,created_at=stamp(),screened_users=len(users),
            comparable_users=len(primary_point),gap=float(primary_point.gap.mean()),bootstrap_iterations=config['bootstrap_iterations'],
            split_iterations=config['split_iterations'],source_hashes=source_hashes,primary_definition_unchanged=True,
            annotation_basis='proposals_pending_review',independently_validated=False,production_enabled=False,reserved_test_opened=False,
            additional_analyses_defined_after_primary=True,skip_certificates_preserved=True)
        atomic_json(pending/'summary.json',summary)
        make_figures(pending,primary_point)
        classifier_diagnostics(settings,study,pending)
        explain(pending)
        # Detect edits during long bootstrap before sealing a report based on stale decisions.
        verify_inputs(study, source_hashes, config_path, base, registry)
        seal(pending,[p.name for p in pending.iterdir() if p.is_file()],status='complete',stage=stage)
        pending.rename(destination)
        return destination


def make_figures(folder,primary):
    from .observational_figures import render_frames
    render_frames(folder,primary,pd.read_csv(folder/'intervals.csv'),pd.read_csv(folder/'sensitivities.csv'))


def classifier_diagnostics(settings,study,folder):
    """Reuse existing model outputs; no additional inference or recalibration."""
    from ..learning import classification_metrics
    base=settings['outputs']/(study.name+'_benchmark_v1')/'benchmark_provisional'
    if not base.exists():raise FileNotFoundError('Falta comparación sellada del benchmark')
    verify_seal(base)
    training=read_csv(study/'training_input/train.csv')
    majority=training.groupby('label').weight.apply(lambda x:x.astype(float).sum()).sort_values(ascending=False).index[0]
    rows=[];curves=[];breakdown=[];ceilings=[];class_rows=[]
    for model in ('robertuito','beto','xlm_roberta'):
        f=read_csv(base/(model+'_pairs.csv'))
        for key in ('gold_target_present','candidate_present','context_complete','accepted'):
            f[key]=f[key].str.lower().eq('true')
        f['weight']=f.weight.astype(float)
        full=classification_metrics(f.label,f.valence,f.weight)
        for label,value in full['classes'].items():class_rows.append(dict(model=model,label=label,**value))
        evaluable=f.label.isin(VALID);den=f.loc[evaluable,'weight'].sum()
        status=np.select([~f.candidate_present,~f.context_complete,~f.accepted,f.valence.isin(VALID)],
                         ['omitted_target','incomplete_context','abstained','accepted_evaluable'],default='accepted_auxiliary')
        for name in np.unique(status[evaluable]):
            mask=evaluable&(status==name)
            breakdown.append(dict(model=model,status=name,pairs=int(mask.sum()),weight=f.loc[mask,'weight'].sum(),share=f.loc[mask,'weight'].sum()/den))
        ceilings.append(dict(model=model,extraction_ceiling=f.loc[evaluable&f.candidate_present,'weight'].sum()/den,
                             context_ceiling=f.loc[evaluable&f.context_complete,'weight'].sum()/den))
        conditional=f.loc[f.candidate_present&f.context_complete].copy()
        conditional['confidence']=pd.to_numeric(conditional.confidence,errors='coerce')
        conditional=conditional.sort_values(['confidence','comment_id','target_id'],ascending=[False,True,True])
        for fraction in np.linspace(.05,1,20):
            k=max(1,int(np.ceil(len(conditional)*fraction)));part=conditional.iloc[:k]
            valid=part.label.isin(VALID)&part.valence.isin(VALID)
            cover=part.loc[valid,'weight'].sum()/den
            correct=part.label.eq(part.valence)
            risk=1-float(np.average(correct,weights=part.weight))
            curves.append(dict(model=model,candidate_fraction=fraction,accepted_pairs=k,integral_coverage=cover,risk=risk,
                               rule='diagnostic confidence ranking; original operational thresholds unchanged'))
        truth=f.label;pred=np.where(f.candidate_present,majority,'omitted')
        metrics=classification_metrics(truth,pred,f.weight)
        rows.append(dict(model='training_majority',matched_model=model,label=majority,macro_f1=metrics['macro_f1'],
                         scope='same extraction omissions and full evaluation denominator; no calibrated acceptance claim'))
        shutil_path=folder/(model+'_confusion.csv')
        import shutil
        shutil.copy2(base/(model+'_confusion.csv'),shutil_path)
    pd.DataFrame(rows).to_csv(folder/'majority_baseline.csv',index=False)
    pd.DataFrame(class_rows).to_csv(folder/'classifier_per_class.csv',index=False)
    pd.DataFrame(curves).to_csv(folder/'risk_coverage.csv',index=False)
    pd.DataFrame(breakdown).to_csv(folder/'coverage_breakdown.csv',index=False)
    pd.DataFrame(ceilings).to_csv(folder/'coverage_ceilings.csv',index=False)
    development=settings['outputs']/study.name/'development_diagnostics'
    verify_seal(development)
    seeds=read_csv(development/'seeds.csv');seeds['macro_f1_weighted']=seeds.macro_f1_weighted.astype(float)
    seeds.groupby('model').macro_f1_weighted.agg(['count','mean','std']).to_csv(folder/'validation_seed_variability.csv')
    import shutil
    shutil.copy2(base/'intervals.csv',folder/'classifier_intervals.csv')
    imported=json.loads((study/'training/comparison.json').read_text())
    enabled=[]
    for model in imported['models']:
        for label,value in model['calibration']['thresholds'].items():
            enabled.append(dict(model=model['model_id'],label=label,threshold=value,enabled=float(value)<=1))
    pd.DataFrame(enabled).to_csv(folder/'enabled_classes.csv',index=False)
    # Distinguish extraction from documented political group; unknown is not an omission status.
    meta=read_csv(study/'annotations/benchmark/sample.csv')
    registry=load_registry(settings['_root']/'config/political_targets_v3.json',frozen=True)
    mapping={t['target_id']:t.get('target_group','unknown') for t in registry['targets']}
    original=read_csv(base/'beto_pairs.csv');original['target_group']=original.target_id.map(mapping).fillna('unknown')
    original['present']=original.candidate_present.str.lower().eq('true');original['gold']=original.gold_target_present.str.lower().eq('true')
    original['weight']=original.weight.astype(float)
    extraction=[]
    for group,part in original.loc[original.gold].groupby('target_group'):
        extraction.append(dict(group=group,targets=len(part),weight=part.weight.sum(),recovered_weight=part.loc[part.present,'weight'].sum(),
                               recall=part.loc[part.present,'weight'].sum()/part.weight.sum()))
    pd.DataFrame(extraction).to_csv(folder/'extraction_by_target_group.csv',index=False)


def explain(folder):
    """Interpretation accompanies every table, including unsupported or adverse results."""
    p=pd.read_csv(folder/'user_scores.csv');ci=pd.read_csv(folder/'intervals.csv').set_index('metric')
    s=pd.read_csv(folder/'sensitivities.csv');split=pd.read_csv(folder/'split_half.csv')
    adverse=pd.read_csv(folder/'adverse_error.csv');ab=json.loads((folder/'AB_comparison.json').read_text())
    tip=json.loads((folder/'adverse_tipping.json').read_text())
    lines=['# Estudio observacional: resultados e interpretación','',
      'Se mantienen 300 usuarios examinados y la definición principal. Los resultados son condicionales a los historiales, actores explícitos y anotaciones actuales; no estiman prevalencia electoral. Las comprobaciones adicionales se definieron después del análisis principal.','',
      '## Selección y composición',
      'exclusion_funnel.csv usa categorías excluyentes; exclusion_overlap.csv permite motivos concurrentes. Los certificados de afinidad no son evidencia de ausencia de polarización. reading_scope.json distingue comentarios no leídos de anotaciones sin objetivos.',
      'selection_observables.csv compara historiales completos, sin depender de cuántos eventos se anotaron. Las diferencias estandarizadas caracterizan selección observable y no corrigen sesgo no observado.',
      'event_composition.csv separa A y B, afinidad, bloque destino y valoración. Cada evento representa un comentario--bloque; varios objetivos del mismo bloque no equivalen a observaciones independientes.','',
      '## Brecha y robustez',
      f'Entre {len(p)} comparables, la media de la brecha es {p.gap.mean():.4f}, la mediana {p.gap.median():.4f} y la media recortada {trimmed(p.gap):.4f}. La concordancia de estas medidas ayuda a evaluar si el promedio se apoya en unos pocos extremos.',
      f'La proporción observada con brecha positiva es {100*p.gap.gt(0).mean():.2f}%; el patrón conjunto de balance interno positivo y externo negativo aparece en {100*(p.in_rate.gt(0)&p.out_rate.lt(0)).mean():.2f}%. No son porcentajes de votantes polarizados.',
      'intervals.csv utiliza usuarios y canales, recalculando afinidad y elegibilidad. Sus intervalos no incorporan error de anotación ni garantizan validez del constructo. Las cuatro celdas de balance_matrix.pdf muestran qué dirección de valoración sostiene la diferencia.',
      'influence.csv retira una persona por vez. La estabilidad del promedio no demuestra que cada puntuación individual sea estable; AP y dispersión todavía dependen del volumen.','',
      '## Soporte individual y estabilidad',
      f'La mediana del soporte en B es {p.evaluation_interactions.median():.1f} eventos y {p.evaluation_videos.median():.1f} videos. support_thresholds.csv permite distinguir amplitud de la muestra y evidencia por persona.',
      f'En A/B se conservan los mismos {ab["users"]} usuarios: brecha A={ab["A"]:.4f}, B={ab["B"]:.4f}, diferencia={ab["difference_A_minus_B"]:.4f}. A participó en la asignación de afinidad: esta comparación diagnostica reutilización y persistencia, no demuestra eliminación de toda circularidad.',
      f'Las {len(split)} divisiones de B tienen una mediana de {split.users.median():.0f} usuarios elegibles y correlaciones medianas Pearson={split.pearson.median():.3f}, Spearman={split.spearman.median():.3f}. Los cuartiles entre particiones son variación de división, no un intervalo de confianza. La pérdida de participantes y el escaso soporte limitan cualquier interpretación como rasgo individual estable.','',
      '## Sensibilidad',
      'sensitivities.csv conserva las seis variantes previas y añade criterios fijos de soporte y afinidad. Cada fila informa usuarios, brecha, intervalo y diferencia sobre los mismos usuarios retenidos. Las variantes pueden cambiar la población; no debe atribuirse todo cambio a la fórmula.',
      'Los mínimos de B, positivos y cuota de afinidad se evalúan en la cuadrícula completa predefinida, no se elige la combinación favorable. La variante sin neutrales cambia el denominador y marca las divisiones vacías como no estimables. Los mixtos ya estaban excluidos.',
      'Las filas source_ describen valoración bajo procedencias editoriales diferentes. Los usuarios pueden aparecer en varias fuentes, y cada fuente retiene quienes permiten calcular ambos balances. No constituyen efectos causales del canal.','',
      '## Sensibilidad adversa al error',
      'adverse_error.csv calcula el peor resultado alcanzable cambiando un presupuesto de eventos de B, conservando afinidad, elegibilidad, extracción y denominadores. Se eligen primero los eventos de mayor influencia, por lo que la curva no representa una tasa de error aleatoria esperada.',
      f'El punto de cruce requiere {tip["minimum_event_changes_for_nonpositive_gap"]} cambios de {tip["B_events"]} eventos ({100*tip["fraction"]:.2f}%). Es una condición adversa del cálculo fijado, no validación de las anotaciones ni robustez del proceso completo.',
      'Cambios en A, errores correlacionados, actores omitidos y abstenciones pueden alterar quién es comparable. No se infiere resistencia a esos errores desde esta curva.','',
      '## Clasificación y extracción',
      'classifier_intervals.csv reproduce los IC por videos ya calculados. validation_seed_variability.csv describe dispersión entre entrenamientos en validación, no repeticiones independientes de la evaluación.',
      'classifier_per_class.csv y las matrices de confusión separan las cinco etiquetas; macro-F1 mantiene la definición vigente. enabled_classes.csv explica qué clases aceptan predicciones bajo la calibración original.',
      'majority_baseline.csv usa la clase con mayor peso de entrenamiento y conserva las omisiones de extracción. Su F1 es una referencia simple; no se presenta como un modelo con aceptación calibrada.',
      'coverage_breakdown.csv separa objetivos omitidos, contexto incompleto, abstención y aceptación auxiliar. coverage_ceilings.csv muestra cuánto puede cubrir cada modelo aun antes del umbral.',
      'risk_coverage.csv ordena candidatos por confianza sin cambiar la operación. El riesgo describe error entre predicciones seleccionadas; la cobertura integral conserva como denominador todos los objetivos evaluables. No permite exigir una cobertura superior al máximo de extracción y contexto.',
      'extraction_by_target_group.csv distingue conocimiento del bloque y recuperación de la mención. Un actor desconocido puede ser recuperado; una referencia solo contextual está fuera del protocolo explícito y no se convierte automáticamente en un falso negativo.','',
      '## Alcance de la conclusión',
      'El promedio, la proporción positiva, los balances y las sensibilidades deben leerse juntos. Un promedio agregado robusto puede coexistir con medición individual poco estable. La diferencia entre afinidades conserva su intervalo y su interpretación inconclusa; no se calcula potencia retrospectiva con el efecto observado.',
      'Las limitaciones incluyen selección de comparables, soporte desigual, concentración en actores, actores sin bloque documentado, captura posterior, plataforma y posibles conductas coordinadas. La reproducibilidad se apoya en código, semillas, huellas y resultados agregados; los historiales identificables y afinidades individuales permanecen locales.']
    (folder/'report.md').write_text('\n\n'.join(lines)+'\n')
