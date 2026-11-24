"""Export English publication tables and figures from the sealed 20261122 report."""
from pathlib import Path
import argparse
import json
import re

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from polarization_pipeline.targeted.publication.state import verify_seal
from polarization_pipeline.targeted.publication.observational_figures import export

NAMES={'robertuito':'RoBERTuito','beto':'BETO','xlm_roberta':'XLM-RoBERTa'}
LABELS={'positive':'Favorable','negative':'Unfavorable','neutral':'Neutral','mixed':'Mixed','not_evaluable':'Not evaluable','omitted':'Omitted'}
VARIANTS={'reverse_A_B':'Reversed A/B','balanced_video':'Video-balanced','exclude_keiko_fujimori':'Without Keiko Fujimori','exclude_roberto_sanchez':'Without Roberto Sánchez','exclude_rafael_lopez_aliaga':'Without Rafael López Aliaga','historical_main_only':'Historical data only','without_neutral_denominator':'Without neutral denominators'}
GROUPS={'izquierda':'Left','derecha':'Right','neutral':'Neutral'}

# Each generated table received a stable label and an explanatory call in the prose.
TABLE_CONTEXT = {
    'Observable participation by inclusion status.': ('selection', 'compared observable participation between included and excluded users'),
    'Summary statistics for comparable users.': ('robust', 'summarized the location, dispersion, and event support of individual measurements'),
    'Comment--bloc events by partition, affinity, target, and evaluation.': ('composition', 'reported how evaluations were distributed across partitions and political destinations'),
    'Original sensitivity variants and matched comparisons.': ('sensitivity', 'compared the original sensitivity variants with the primary definition on matched users'),
    'Fixed grid of event-support and affinity criteria.': ('grid', 'reported retention and normalized gaps across the fixed threshold grid'),
    'Event support, neutral denominators, and source provenance.': ('support', 'reported the additional support, denominator, and source-specific checks'),
    'Worst-case gap after changing a budget of B evaluations.': ('adverse', 'reported the conditional worst-case gap under each error budget'),
    'Five-model end-to-end results and video-bootstrap uncertainty.': ('five_models', 'reported the five models\' end-to-end performance and accepted predictions'),
    'Common complete-context candidates: classification and accepted share.': ('common', 'reported classification conditional on the shared complete-context inputs'),
    'End-to-end results and video-bootstrap uncertainty.': ('reference_intervals', 'reported the original reference models\' performance and uncertainty'),
    'Per-class performance before abstention, including omissions.': ('classes', 'located class-specific errors before confidence selection'),
    'Weighted validation macro-F1 across three training seeds.': ('seeds', 'reported between-seed variability on validation data'),
    'Confusion matrices: weighted percentages within reference rows.': ('confusion', 'reported the weighted confusion patterns within each reference class'),
    'Coverage decomposition over all evaluable target weight.': ('coverage', 'separated losses from extraction, incomplete context, and abstention'),
}

def num(x,d=3):
    x=float(x)
    return f'{x:.{d}f}' if np.isfinite(float(x)) else '---'

def table(caption,headers,rows,spec=None,note=None):
    if caption not in TABLE_CONTEXT:
        raise ValueError('A generated table requires an explanatory reference')
    key, explanation = TABLE_CONTEXT[caption]
    label='tab:supp_'+key
    spec=spec or 'l'+'r'*(len(headers)-1)
    return '\n'.join([r'Table~\ref{'+label+'} '+explanation+'.\n',
        r'\begin{table}[H]\centering\small',r'\caption{'+caption+'}',r'\label{'+label+'}',
        r'\setlength{\tabcolsep}{4pt}',r'\begin{tabular}{'+spec+r'}\toprule',
        ' & '.join(headers)+r'\\\midrule',*[' & '.join(map(str,row))+r'\\' for row in rows],
        r'\bottomrule\end{tabular}',r'\par\smallskip\footnotesize '+note if note else '',r'\end{table}'])

def build(report,root,model_report=None):
    verify_seal(report)
    summary=json.loads((report/'summary.json').read_text())
    if summary['analysis_id'] != 'observational_strengthening_20261122_v1' or summary['screened_users'] != 300:
        raise ValueError('This narrative edition applies only to observational_strengthening_20261122_v1')
    read=lambda n:pd.read_csv(report/n)
    parts=[r'''\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[spanish,english,es-noshorthands]{babel}
\usepackage[margin=2cm]{geometry}
\usepackage{amsmath,booktabs,graphicx,float,url}
\title{Supplementary Material: Expressed Affective Polarization in YouTube Comments}
\author{}
\date{November 22, 2026}
\begin{document}\maketitle
This material expanded the observational study's tables and diagnostics. Measurement units were comparable users for affective polarization and comment--target pairs for classifier evaluation. Complementary analyses were defined after the primary result to examine scope and stability rather than to select specifications by significance. This edition concerned 300 examined histories and the three reference classifiers already evaluated.
\section{Selection and measurement evidence}
The 4\,443 structural candidates were not already comparable users. Of the first 300 examined in the fixed order, 174 failed affinity requirements, 126 met them, and 122 also qualified in B. Among the four remaining exclusions, one lacked ingroup evidence, two lacked outgroup evidence, and one had insufficient B events. This hierarchy gave mutually exclusive reasons; one outgroup absence also coincided with insufficient events. Early exclusions based on the affinity criteria left 709 comments unread in 56 excluded histories, rather than annotating them as target absence. Comparable-user histories were read completely.

Videos were assigned by hash with seed 42 to disjoint sets A (affinity assignment) and B (evaluation); the sets were not chronological periods. Reading started with A, ordering videos by size and breaking ties by identifier. Remaining comments were skipped only when a conservative bound proved that neither bloc could meet the affinity requirements, even if every unread comment was counted as possible support. Skipped observations remained missing rather than being labeled as target absence. Users meeting the affinity criteria required complete reading of both A and B.

The shared training recipe used seeds 42, 43, and 44, AdamW with learning rate $2\times10^{-5}$, weight decay 0.01, effective batch size 16, at most eight epochs, and early stopping after two epochs without validation improvement. These settings remained fixed in the encoder extension. Probabilities were averaged across the three seeds before calibration on validation data.

''']
    sel=read('selection_observables.csv');rows=[]
    for var,name in [('comments','Comments'),('videos','Videos'),('channels','Channels'),('source_groups','Source groups')]:
        d=sel[sel.variable.eq(var)]
        if d.empty:continue
        a=d[d.group.eq('included')].iloc[0];b=d[d.group.eq('excluded')].iloc[0]
        fmt=lambda x:f'{num(x["median"],2)} [{num(x.q25,2)}, {num(x.q75,2)}]'
        rows.append([name,fmt(a),fmt(b),num(a.standardized_difference)])
    parts.append(table('Observable participation by inclusion status.',['Variable','Included (122)','Excluded (178)','SMD'],rows,
        note='Values were median [25th, 75th percentile]. SMD: standardized mean difference.'))
    parts.append('Positive SMDs indicated greater mean activity among comparable users. These described observable selection; they neither corrected unobserved differences nor justified generalization to all YouTube users.')
    robust=read('robust_statistics.csv');rows=[]
    for _,a in robust[robust.group.eq('all')].iterrows():
        name={'AP_In':r'$\mathrm{AP}_{In}$','AP_Out':r'$\mathrm{AP}_{Out}$','AP_target':'AP','spread':'Dispersion','gap':'Normalized gap','N_in':'Ingroup events','N_out':'Outgroup events','evaluation_interactions':'B events','evaluation_videos':'B videos'}[a.metric]
        rows.append([name,num(a['mean']),num(a.sd),num(a['median']),f'[{num(a.q25)}, {num(a.q75)}]',num(a.trimmed10)])
    parts.append(table('Summary statistics for comparable users.',['Metric','Mean','SD','Median','IQR',r'10\% trimmed mean'],rows,
        note=r'SD: standard deviation. IQR was reported as [25th, 75th percentile]. The trimmed mean removed 10\% of observations from each tail.'))
    parts.append('Normalization and equal contribution per user reduced the influence of high activity on the aggregate contrast. They did not remove uncertainty in short histories. Median support of eight B events and six B videos was therefore relevant to the interpretation of individual scores.')
    composition=read('event_composition.csv');rows=[]
    for (fold,aff,target),d in composition.groupby(['fold','ingroup','target_group']):
        counts=d.set_index('valence').events
        rows.append([fold,GROUPS[aff],GROUPS[target],*[str(int(counts.get(l,0))) for l in LABELS if l!='omitted']])
    parts.append(table('Comment--bloc events by partition, affinity, target, and evaluation.',['Partition','Affinity','Target','Fav.','Unfav.','Neutral','Mixed','Not eval.'],rows,
        note='Mixed and not-evaluable events did not contribute to balances. Counts were events, not independent people.'))
    parts.append(r'\section{Sensitivity of the normalized gap}')
    sens=read('sensitivities.csv');rows=[]
    for _,a in sens.iloc[:6].iterrows():
        rows.append([VARIANTS[a.variant],int(a.users),num(a.gap),f'[{num(a.ci_low)}, {num(a.ci_high)}]',num(a.baseline_same_users),f'[{num(a.difference_ci_low)}, {num(a.difference_ci_high)}]'])
    parts.append(table('Original sensitivity variants and matched comparisons.',['Variant','Users','Gap',r'95\% CI','Original','Change CI'],rows,
        note=r'Original: primary gap restricted to the retained users. Change CI: 95\% interval for the paired change.'))
    parts.append('Changes in retained population and changes in measurement were distinct. Comparing variants with the original definition on the same users avoided attributing selection differences to the formula. No paired-change interval for these six variants excluded zero; this did not demonstrate equivalence.')
    grid=sens[sens.variant.str.startswith('grid_')];rows=[]
    for _,a in grid.iterrows():
        e,share,p=re.fullmatch(r'grid_events(\d+)_share([0-9.]+)_positive(\d+)',a.variant).groups()
        label=f'e={e}, s='+('2/3' if float(share)<.7 else '3/4')+f', p={p}'
        rows.append([label,int(a.users),num(a.gap),f'[{num(a.ci_low)}, {num(a.ci_high)}]'])
    parts.append(table('Fixed grid of event-support and affinity criteria.',['Criterion','Users','Gap',r'95\% CI'],rows,
        note='e: minimum B events; s: dominant positive share in A; p: minimum A positives. Two positive A videos remain required.'))
    parts.append('The grid resampled the 300 examined users and allowed relaxed criteria to admit users with complete histories. Early exclusions received no imputed labels. Consequently, the original-threshold row could have a slightly different interval from the bootstrap conditional on the 122 original comparables. Changes in the grid reflected retention because the individual scoring formula remained fixed.')
    rows=[]
    for _,a in sens.iloc[18:].iterrows():
        label=VARIANTS.get(a.variant,a.variant.replace('_',r'\_'))
        if a.variant.startswith('support_'):label='Events per bloc: '+a.variant.rsplit('_',1)[-1]
        if a.variant.startswith('source_'):label=GROUPS[a.variant.rsplit('_',1)[-1]]+' sources'
        rows.append([label,int(a.users),num(a.gap),f'[{num(a.ci_low)}, {num(a.ci_high)}]'])
    parts.append(table('Event support, neutral denominators, and source provenance.',['Variant','Users','Gap',r'95\% CI'],rows,
        note='Source-specific subsets could overlap and required both target blocs within each subset.'))
    parts.append('Requiring five events per bloc retained 30 users and widened uncertainty. Removing neutral events from denominators retained 114: the gap rose from 1.4827 to 1.6687 on those same users, a change of 0.1859 [0.0897, 0.2883]. The primary definition preserved neutral evidence and moderated magnitude. Eight users lost positive denominators in the variant. Mixed events had already been excluded; removing them again did not constitute an additional sensitivity analysis.')
    parts.append(r'''\section{Individual stability and adverse errors}
Among 113 users measurable in A and B, the mean A gap was 1.5810 and the mean B gap 1.4152. A minus B was 0.1658, 95\% CI [$-0.0494$, 0.3290]. The point estimate was compatible with optimism from reusing A, but the interval did not demonstrate inflation. Separating A/B was justified by design rather than by obtaining this contrast.

The 200 random B-video splits retained A affinity, required two events and both blocs in each half, and compared only users measurable in both. They retained 51--74 users (median 63). Median Pearson correlation was 0.3667, IQR [0.3032, 0.4203]; median Spearman correlation was 0.3806, IQR [0.3272, 0.4448]. These described variation across partitions, not confidence intervals or population reliability. The aggregate direction was more stable than individual ordering \cite{Pronk2022SplitHalf}.
''')
    adverse=read('adverse_error.csv');rows=[[f'{100*a.budget:.0f}'+r'\%',int(a.changed_events),num(a.worst_case_gap)] for _,a in adverse.iterrows()]
    parts.append(table('Worst-case gap after changing a budget of B evaluations.',['Budget','Changed events','Minimum gap'],rows,
        note='Affinity, users, targets, and denominators remained fixed.'))
    parts.append(r'Events with the largest influence were changed first toward ingroup rejection or outgroup support. The mean became nonpositive after 193 of 1\,609 directed changes (12.00\%). This deterministic conditional bound neither estimated actual error frequency nor included errors in A, extraction, unknown targets, or selection. A global classifier confusion matrix was not transferred to histories because their distributions and abstention differed \cite{Egami2023Surrogates}.')
    if model_report is not None:
        model_report = Path(model_report)
        verify_seal(model_report)
        from polarization_pipeline.targeted.publication.observational_manuscript import NAMES as ALL_NAMES, model_block
        from polarization_pipeline.targeted.publication.model_statistics import intervals
        common_ci = intervals(model_report)
        model_block(model_report)  # Validate estimates and both interval panels before writing.
        comparison = pd.read_csv(model_report/'comparison.csv')
        ci = pd.read_csv(model_report/'intervals.csv')
        expected = {(m,p) for m in ALL_NAMES for p in ('end_to_end','common_complete_candidates')}
        if set(zip(comparison.model_id,comparison.panel)) != expected or comparison.duplicated(['model_id','panel']).any():
            raise ValueError('Incomplete five-model comparison')
        parts.append(r'\section{Five-model evaluation and accepted predictions}')
        model_summary=json.loads((model_report/'summary.json').read_text())
        integral_pairs=int(comparison.loc[comparison.panel.eq('end_to_end'),'pairs'].iloc[0])
        common_pairs=int(comparison.loc[comparison.panel.eq('common_complete_candidates'),'pairs'].iloc[0])
        parts.append(f"This section included RoBERTuito, BETO, XLM-RoBERTa, MrBERT-es, and mDeBERTa-v3-base on the same {model_summary['comments']:,}-comment evaluation sample. The integral union had {integral_pairs:,} pairs; the common complete-context panel had {common_pairs:,}. Sampling weights were retained. F1 was measured before abstention; accepted precision and coverage used the original validation calibration without refitting on this sample.")
        rows=[]
        for model,name in ALL_NAMES.items():
            for metric,label,mult in [('macro_f1','Macro-F1',1),('coverage',r'Coverage (\%)',100),('positive_precision','Favorable precision',1),('negative_precision','Unfavorable precision',1)]:
                a=ci[ci.model_id.eq(model)&ci.metric.eq(metric)].iloc[0]
                rows.append([name,label,num(mult*a.estimate),f'[{num(mult*a.ci_low)}, {num(mult*a.ci_high)}]'])
        parts.append(table('Five-model end-to-end results and video-bootstrap uncertainty.',['Model','Metric','Estimate',r'95\% CI'],rows,
            note='Intervals used 2,000 video-bootstrap replicates. Coverage was the accepted share of evaluable target weight. A dash indicated no accepted predictions or insufficient support, not zero precision.'))
        rows=[]
        for model,name in ALL_NAMES.items():
            a=comparison[comparison.model_id.eq(model)&comparison.panel.eq('common_complete_candidates')].iloc[0]
            b=common_ci[common_ci.model_id.eq(model)&common_ci.metric.eq('macro_f1')].iloc[0]
            rows.append([name,num(a.macro_f1,4),f'[{num(b.ci_low,4)}, {num(b.ci_high,4)}]',num(100*a.coverage,2)])
        parts.append(table('Common complete-context candidates: classification and accepted share.',['Model','Macro-F1',r'95\% CI',r'Coverage (\%)'],rows,
            note='Conditional results excluded extraction omissions and were not end-to-end coverage. The same video resampling design was used for the macro-F1 intervals.'))
        parts.append('RoBERTuito retained the largest end-to-end macro-F1. BETO and MrBERT-es showed no clear difference in that metric, without establishing equivalence. MrBERT-es accepted favorable and unfavorable predictions; mDeBERTa accepted favorable only. Neither new model enabled neutral predictions under the stored calibration. Validation precision thresholds were selection rules and did not guarantee the same precision on this evaluation sample.')
        parts.append('The following historical diagnostics retained their original three-reference scope; their confusion matrices, seed variability, loss decomposition, and confidence curves were not presented as five-model results.')
    parts.append(r'\section{Reference-classifier diagnostics}')
    parts.append(r'These diagnostics concerned only the evaluated RoBERTuito, BETO, and XLM-RoBERTa references. The weighted training-majority class was unfavorable: predicting it for available candidates while preserving omissions yielded end-to-end macro-F1 0.1524. This was neither calibrated coverage nor an independent reference. All three models outperformed its F1, but their results did not justify automatic measurement across the full collection \cite{GrimmerStewart2013}.')
    if model_report is None:
        ci=read('classifier_intervals.csv');rows=[]
        for model,name in NAMES.items():
            for metric,label,mult in [('macro_f1','Macro-F1',1),('coverage',r'Coverage (\%)',100),('positive_precision','Favorable precision',1),('negative_precision','Unfavorable precision',1)]:
                a=ci[ci.model_id.eq(model)&ci.metric.eq(metric)].iloc[0]
                rows.append([name,label,num(mult*a.estimate),f'[{num(mult*a.ci_low)}, {num(mult*a.ci_high)}]'])
        parts.append(table('End-to-end results and video-bootstrap uncertainty.',['Model','Metric','Estimate',r'95\% CI'],rows,
            note='Intervals used 2,000 replicates. Precision was computed after abstention; F1 before abstention.'))
    per=read('classifier_per_class.csv');rows=[]
    for model,name in NAMES.items():
        for _,a in per[per.model.eq(model)].iterrows():rows.append([name,LABELS[a.label],num(a.precision),num(a.recall),num(a.f1),int(a.support)])
    parts.append(table('Per-class performance before abstention, including omissions.',['Model','Class','Precision','Recall','F1','Pairs'],rows,
        note='Metrics used sampling weights; support was the raw number of pairs.'))
    parts.append('Primary macro-F1 averaged favorable, unfavorable, and neutral. Mixed and not evaluable were shown to locate errors without changing that definition. Neutral had particularly low F1 and was disabled by original calibration in all references, as were mixed and not evaluable. RoBERTuito and BETO accepted favorable and unfavorable predictions; XLM-RoBERTa accepted favorable only. Acceptance required weighted validation precision of at least 0.85 and at least ten accepted comment--target pairs per class. Both values were study-defined heuristics: the precision target prioritized reliability among retained predictions, and the count requirement avoided enabling a class on very few cases. Ten referred to the raw number of accepted pairs, without adjustment for sampling weights or dependence within comments or videos; it did not establish statistical sufficiency. These criteria did not provide an out-of-sample precision guarantee. Selective classification motivated the error--coverage tradeoff \\cite{Geifman2017Selective}, and temperature scaling supplied the probability-calibration method \\cite{Guo2017Calibration}; neither reference prescribed these numerical values. Evaluation-sample results did not modify the stored acceptance rules.')
    seeds=read('validation_seed_variability.csv');rows=[]
    for model,name in NAMES.items():
        a=seeds[seeds.model.eq(model)].iloc[0];rows.append([name,int(a['count']),num(a['mean'],4),num(a['std'],4)])
    parts.append(table('Weighted validation macro-F1 across three training seeds.',['Model','Seeds','Mean','SD'],rows,
        note='SD: standard deviation between fits. These were validation scores, not repeated independent evaluation samples.'))
    parts.append('The ensemble averaged probabilities, so its F1 was not the mean of per-seed F1. BERTIN remained in historical files only, outside the active comparison.')
    rows=[]
    for model,name in NAMES.items():
        d=read(model+'_confusion.csv').pivot(index='label',columns='valence',values='weight').fillna(0)
        normalized=d.div(d.sum(axis=1),axis=0)*100
        for label in LABELS:
            if label=='omitted':continue
            rows.append([name,LABELS[label],*[num(normalized.get(pred,pd.Series(dtype=float)).get(label,0),1) for pred in LABELS]])
    parts.append(table('Confusion matrices: weighted percentages within reference rows.',['Model','Reference','F','U','N','M','NE','O'],rows,
        note='Predictions: favorable (F), unfavorable (U), neutral (N), mixed (M), not evaluable (NE), omitted (O).'))
    parts.append(r'\subsection*{Coverage losses and confidence ordering}')
    cov=read('coverage_breakdown.csv');rows=[]
    for model,name in NAMES.items():
        d=cov[cov.model.eq(model)].set_index('status')
        rows.append([name,*[num(100*d.loc[s,'share'],2) for s in ['omitted_target','incomplete_context','abstained','accepted_evaluable']]])
    parts.append(table('Coverage decomposition over all evaluable target weight.',['Model','Omitted','Incomplete context','Abstained','Accepted'],rows,
        note='Percentages summed to 100 within each model.'))
    parts.append(r'Recall across all targets, including unknown-bloc actors, was 44.53\%. By actor bloc, recall was 86.36\% for right, 82.09\% for left, and 22.76\% for unknown. Unknown bloc and omitted mention were distinct: some unknown actors were extracted and some known actors omitted. For evaluable targets, the extraction ceiling was 44.07\%; requiring complete context reduced RoBERTuito\textquotesingle s ceiling to 39.47\%. Thus 40\% end-to-end coverage was unattainable for that reference with the current inputs.')
    parts.append(r'''\begin{figure}[H]\centering
\includegraphics[width=0.9\textwidth]{docs/figures/observational_risk_coverage.pdf}
\caption{Weighted error among selected predictions versus end-to-end coverage when candidates were ranked by confidence. This was a diagnostic, not operational threshold recalibration.}\label{fig:supp_risk_coverage}\end{figure}
Figure~\ref{fig:supp_risk_coverage} illustrated the error--coverage tradeoff. Confidence could not recover absent targets: accepting all candidates still left substantial coverage losses. These curves examined quality and reach together, without choosing a new threshold based on favorable evaluation performance.
\section{Scope and status of this edition}
The limit of 300 examined users was set for resource reasons after annotation progress was known, including 79 comparable users among the first 200. It replaced the original target of 800 comparable users and was not fixed before the study began. The observed gap's 95\% CI half-width was 0.2047, compared with the planned 0.20. The planning target was treated as a precision assumption rather than a universal publication threshold \cite{lakens2022sample}; sampling was not extended in response to the result.

This material accompanied a preprint with provisional results. At the time this version was prepared, history and evaluation annotations remained pending individual human review. Intervals did not include annotation error, and classifier results expressed agreement with initial annotations. Adversarial sensitivity did not replace their confirmation. Model expansion was chosen after examining this sample and was not an independent final evaluation.

Results concerned expressions toward political actors among users with evidence in both blocs. They did not identify the electorate, voting intention, channel causality, or hostility toward every supporter of an opposing bloc. Channel selection, short histories, the registry with 22 documented-bloc identities out of 124, and possible coordinated accounts limited scope. Bots were not identified through a validated procedure. Retrospective capture could not recover deleted content or all original text states. Public tables reported aggregates; identifiers and sensitive affinity inferences required protection and were excluded from figures and tables.
\bibliographystyle{IEEEtran}
\bibliography{docs/references}
\end{document}
''')
    if model_report is not None:
        parts[0]=parts[0].replace('This edition concerned 300 examined histories and the three reference classifiers already evaluated.', 'This edition concerned 300 examined histories and the five-model evaluation, with additional diagnostics for the three original references.')
    (root/'docs/observational_supplement.tex').write_text('\n\n'.join(parts))
    if model_report is not None:
        return  # Retain the existing reference figures and observational graphics.
    export(report,root/'docs/figures')
    with plt.rc_context({'font.size':10,'pdf.fonttype':42}):
        fig,ax=plt.subplots(figsize=(6.3,3.5))
        curves=read('risk_coverage.csv')
        for model,name in NAMES.items():
            d=curves[curves.model.eq(model)];ax.plot(100*d.integral_coverage,100*d.risk,label=name)
        ax.set(xlabel='End-to-end coverage (%)',ylabel='Error among selected predictions (%)',xlim=(0,50))
        ax.legend();ax.grid(alpha=.2);fig.tight_layout()
        for ext in ['pdf','png']:fig.savefig(root/'docs/figures'/('observational_risk_coverage.'+ext),dpi=220)
        plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True)
    p.add_argument('--root',type=Path,default=Path.cwd());p.add_argument('--model-report',type=Path);a=p.parse_args();build(a.report,a.root,a.model_report)
