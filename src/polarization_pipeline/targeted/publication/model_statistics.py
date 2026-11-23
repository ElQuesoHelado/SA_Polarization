"""Derived common-context uncertainty; never rewrite the source comparison."""
from pathlib import Path
import numpy as np
import pandas as pd

from ..common import read_csv, sha256
from ..learning import classification_metrics
from .state import seal, verify_seal

MODELS = ('robertuito', 'beto', 'xlm_roberta', 'mrbert_es', 'mdeberta_v3')


def prepare(report, sample_path, *, seed=57, iterations=2000):
    report, sample_path = Path(report), Path(sample_path)
    verify_seal(report)
    if iterations < 10:
        raise ValueError('At least ten bootstrap replicates are required')
    provenance = dict(comparison_sha256=sha256(report/'manifest.json'),
                      sample_sha256=sha256(sample_path), seed=seed, iterations=iterations)
    destination = report.parent/'manuscript_statistics'
    if destination.exists():
        manifest = verify_seal(destination)
        if any(manifest.get(k) != v for k, v in provenance.items()):
            raise ValueError('Derived intervals belong to another comparison or bootstrap')
        return destination
    sample = read_csv(sample_path, usecols=['comment_id', 'post_id'])
    if sample.comment_id.duplicated().any() or sample.empty:
        raise ValueError('Invalid evaluation-sample identities')
    frames = {m: read_csv(report/f'{m}_pairs.csv') for m in MODELS}
    common = None
    metadata = sample.set_index('comment_id').post_id
    for frame in frames.values():
        if frame.duplicated(['comment_id', 'target_id']).any() or not frame.post_id.eq(frame.comment_id.map(metadata)).all():
            raise ValueError('Pair identities differ from the evaluation sample')
        valid = frame.context_complete.str.lower().eq('true') & frame.candidate_present.str.lower().eq('true')
        keys = set(zip(frame.loc[valid, 'comment_id'], frame.loc[valid, 'target_id']))
        common = keys if common is None else common & keys
    if not common:
        raise ValueError('No shared complete-context candidates')
    points = read_csv(report/'comparison.csv')
    selected, positions = {}, {}
    videos = sample.post_id.unique()
    video_index = {v: i for i, v in enumerate(videos)}
    for model, frame in frames.items():
        frame = frame.loc[[k in common for k in zip(frame.comment_id, frame.target_id)]].copy()
        weights = frame.weight.to_numpy(float)
        if not np.isfinite(weights).all() or (weights <= 0).any():
            raise ValueError('Invalid sampling weights')
        expected = points.loc[points.model_id.eq(model) & points.panel.eq('common_complete_candidates')]
        score = classification_metrics(frame.label, frame.valence, weights)['macro_f1']
        if len(expected) != 1 or len(frame) != int(expected.iloc[0].pairs) or not np.isclose(score, float(expected.iloc[0].macro_f1), atol=1e-12, rtol=0):
            raise ValueError('Common panel does not reproduce the sealed comparison')
        selected[model] = frame
        positions[model] = frame.post_id.map(video_index).to_numpy(int)
    rng = np.random.default_rng(seed)
    draws = {m: [] for m in MODELS}
    for _ in range(iterations):
        counts = rng.multinomial(len(videos), np.full(len(videos), 1/len(videos)))
        for model, frame in selected.items():
            weights = frame.weight.to_numpy(float)*counts[positions[model]]
            if weights.sum() > 0:
                draws[model].append(classification_metrics(frame.label, frame.valence, weights)['macro_f1'])
    rows = []
    for model in MODELS:
        values = np.asarray(draws[model])
        enough = len(values) >= max(10, .8*iterations)
        low, high = np.quantile(values, [.025, .975]) if enough else (np.nan, np.nan)
        estimate = float(points.loc[points.model_id.eq(model) & points.panel.eq('common_complete_candidates'), 'macro_f1'].iloc[0])
        rows.append(dict(model_id=model, metric='macro_f1', estimate=estimate,
                         ci_low=low, ci_high=high, valid_replicates=len(values),
                         status='estimated' if enough else 'insufficient_support'))
    destination.mkdir()
    pd.DataFrame(rows).to_csv(destination/'common_context_intervals.csv', index=False)
    seal(destination, ['common_context_intervals.csv'], **provenance,
         panel='common_complete_candidates', bootstrap_unit='video', production_enabled=False)
    return destination


def intervals(report):
    """Bind the derivative to the original report before exposing any numbers."""
    report = Path(report)
    destination = report.parent/'manuscript_statistics'
    manifest = verify_seal(destination)
    if manifest.get('comparison_sha256') != sha256(report/'manifest.json'):
        raise ValueError('Intervals belong to another comparison')
    return read_csv(destination/'common_context_intervals.csv')
