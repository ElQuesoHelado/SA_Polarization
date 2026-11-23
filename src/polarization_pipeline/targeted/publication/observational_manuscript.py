"""Guarded integration of verified classifier results into the active preprint."""
from pathlib import Path
import json
import math
import re
import shutil
import subprocess

from ..common import atomic_json, read_csv, sha256, stamp
from .state import verify_seal

NAMES = dict(robertuito='RoBERTuito', beto='BETO', xlm_roberta='XLM-RoBERTa',
             mrbert_es='MrBERT-es', mdeberta_v3='mDeBERTa-v3-base')
BEGIN = '% BEGIN OBSERVATIONAL MODEL RESULTS'
END = '% END OBSERVATIONAL MODEL RESULTS'


def model_block(report):
    verify_seal(report)
    frame = read_csv(report / 'comparison.csv')
    models = list(NAMES)
    required_panels = {'end_to_end', 'common_complete_candidates'}
    required = {(model,panel) for model in models for panel in required_panels}
    if (set(zip(frame.model_id,frame.panel)) != required or
            frame.duplicated(['model_id','panel']).any()):
        raise ValueError('Comparación incompleta o duplicada; se requieren cinco modelos')
    if any(not math.isfinite(float(v)) or not 0 <= float(v) <= 1
           for metric in ('macro_f1','coverage') for v in frame[metric]):
        raise ValueError('Métricas de comparación inválidas')
    for panel in required_panels:
        counts=frame.loc[frame.panel.eq(panel),'pairs'].astype(int)
        if counts.nunique()!=1 or counts.iloc[0]<=0:
            raise ValueError('Denominadores incompatibles dentro del panel')
    global_rows = frame.loc[frame.panel.eq('end_to_end')].set_index('model_id')
    common = frame.loc[frame.panel.eq('common_complete_candidates')].set_index('model_id')
    from .model_statistics import intervals
    integral_ci = read_csv(report/'intervals.csv')
    common_ci = intervals(report)

    def bounds(data, model, estimate):
        rows = data.loc[data.model_id.eq(model) & data.metric.eq('macro_f1')]
        if len(rows) != 1:
            raise ValueError('Intervalos ausentes o duplicados')
        row = rows.iloc[0]
        if not math.isclose(float(row.estimate), float(estimate), abs_tol=1e-12):
            raise ValueError('Intervalo incompatible con la estimación')
        if row.status != 'estimated':
            return '---'
        low, high = float(row.ci_low), float(row.ci_high)
        if not (math.isfinite(low) and math.isfinite(high) and 0 <= low <= high <= 1):
            raise ValueError('Intervalo inválido')
        return f'[{low:.4f}, {high:.4f}]'

    count = lambda x: f'{int(x):,}'.replace(',', r'\,')
    lines = [BEGIN, r'\begin{table*}[t]\centering\small',
        r'\caption{Targeted sentiment classification before abstention. Intervals used video bootstrap resampling; the panels retained different evaluation denominators.}',
        r'\label{tab:clasificadores}', r'\begin{tabular}{lrrrr}\toprule',
        r'& \multicolumn{2}{c}{End-to-end evaluation} & \multicolumn{2}{c}{Common complete context}\\',
        r'Model & Macro-F1 & 95\% CI & Macro-F1 & 95\% CI\\\midrule']
    for model in models:
        a,b=global_rows.loc[model],common.loc[model]
        lines.append(f'{NAMES[model]} & {float(a.macro_f1):.4f} & {bounds(integral_ci,model,a.macro_f1)} & {float(b.macro_f1):.4f} & {bounds(common_ci,model,b.macro_f1)}'+r'\\')
    lines += [r'\bottomrule\end{tabular}\end{table*}', '']
    best_f=global_rows.macro_f1.astype(float).idxmax()
    lines.append(r'Table~\ref{tab:clasificadores} compared five models on '+count(global_rows.iloc[0]['pairs'])+
        ' annotation--prediction pairs in the end-to-end evaluation and '+count(common.iloc[0]['pairs'])+
        ' shared complete-context candidates. End-to-end scores included extraction omissions, whereas the common panel isolated classification on available inputs. '
        f'{NAMES[best_f]} had the highest end-to-end macro-F1 ({float(global_rows.loc[best_f,"macro_f1"]):.4f}). '
        'The larger scores on complete-context inputs showed why classifier performance and the ability to recover all political targets had to be distinguished.')
    contrasts = read_csv(report/'model_contrasts.csv')
    if best_f == 'robertuito':
        relevant = contrasts.loc[contrasts.left.eq(best_f) | contrasts.right.eq(best_f)]
        if len(relevant) == 4 and relevant.p_holm.astype(float).lt(.05).all():
            lines.append('RoBERTuito exceeded each alternative in end-to-end macro-F1 under video-bootstrap contrasts with Holm adjustment. The two additional pretrained bases did not improve on that reference in this sample.')
    pair = contrasts.loc[(contrasts.left.eq('beto') & contrasts.right.eq('mrbert_es')) | (contrasts.left.eq('mrbert_es') & contrasts.right.eq('beto'))]
    if len(pair) == 1 and float(pair.iloc[0].p_holm) >= .05:
        lines.append('The comparison detected no clear difference between BETO and MrBERT-es; this did not establish equivalence. Model differences combined architecture, pretraining, and tokenization rather than identifying a causal effect of any one component.')
    low, high = global_rows.coverage.astype(float).agg(['min','max'])
    lines.append(f'Accepted predictions covered {100*low:.1f}--{100*high:.1f}'+r'\% of evaluable target weight across models, limiting automatic expansion; the supplement reported model-specific coverage, accepted precision, and extraction and abstention diagnostics. '
        'The polarization estimates came from annotated user histories and retained their own users and denominators; classifier outputs were not assigned to the full comment collection.')
    lines.append(END)
    return '\n'.join(lines)


def refresh_models(report, controller_folder):
    """No source writes until a separately registered editorial guard matches."""
    controller_folder=Path(controller_folder); report=Path(report)
    guard_path=controller_folder/'observational_manuscript_guard.json'
    pending=controller_folder/'manuscript_update_pending.json'
    if not guard_path.exists():
        atomic_json(pending,dict(reason='observational_manuscript_not_ready',comparison=str(report),user_edits_preserved=True))
        return 'pending_observational_manuscript'
    guard=json.loads(guard_path.read_text());root=Path(guard['root'])
    for name,digest in guard['sources'].items():
        if sha256(root/name)!=digest:
            atomic_json(pending,dict(reason='source_changed',changed_source=name,comparison=str(report),user_edits_preserved=True))
            return 'pending_source_changed'
    source=root/'docs/doc_a_modificar.tex';original=source.read_text()
    if original.count(BEGIN)!=1 or original.count(END)!=1:
        raise ValueError('Marcadores de comparación ausentes o duplicados')
    if 'model_sample' in guard:
        from .model_statistics import prepare
        prepare(report, Path(guard['model_sample']), seed=guard.get('bootstrap_seed',57),
                iterations=guard.get('bootstrap_iterations',2000))
    block=model_block(report)
    updated=re.sub(re.escape(BEGIN)+r'.*?'+re.escape(END),lambda _:block,original,flags=re.S)
    updated=updated.replace('a six-fit extension for MrBERT-es and mDeBERTa-v3-base is underway',
        'a six-fit extension for MrBERT-es and mDeBERTa-v3-base was completed')
    destination=Path(guard['output'])/('modelos_'+stamp().replace(':','').replace('.',''))
    destination.mkdir(parents=True,exist_ok=False)
    (destination/'antes.tex').write_text(original)
    if sha256(source)!=guard['sources']['docs/doc_a_modificar.tex']:
        raise RuntimeError('Edición concurrente del documento')
    source.write_text(updated)
    try:
        with (destination/'latexmk.log').open('w') as log:
            subprocess.run(['latexmk','-pdf','-interaction=nonstopmode','-halt-on-error','-outdir='+str(destination/'build'),str(source)],
                           cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
    except Exception:
        if source.read_text()==updated:source.write_text(original)
        raise
    shutil.copy2(destination/'build/doc_a_modificar.pdf',destination/'doc_a_modificar.pdf')
    shutil.copy2(source,destination/source.name)
    atomic_json(destination/'verification.json',dict(comparison=str(report),comparison_sha256=sha256(report/'manifest.json'),
        source_sha256=sha256(source),pdf_sha256=sha256(destination/'doc_a_modificar.pdf')))
    atomic_json(controller_folder/'manuscript_update_complete.json',dict(pdf=str(destination/'doc_a_modificar.pdf'),source_sha256=sha256(source)))
    return str(destination/'doc_a_modificar.pdf')
