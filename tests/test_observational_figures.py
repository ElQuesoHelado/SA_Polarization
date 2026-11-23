"""Keep the main measurement plots separate, readable, and numerically faithful."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from polarization_pipeline.targeted.common import sha256
from polarization_pipeline.targeted.publication.state import seal
from polarization_pipeline.targeted.publication import observational_figures as figures


class PublicationFigureTests(unittest.TestCase):
    def frames(self):
        primary=pd.DataFrame(dict(gap=[0.,1.,2.],N_in=[1,4,10],N_out=[2,4,12]))
        rows=[]
        for a in figures.GROUPS:
            for b in figures.GROUPS:
                value=.6 if a==b else -.8
                rows.append(dict(metric='balance_'+a+'_'+b,estimate=value,ci_low=value-.1,ci_high=value+.1))
        intervals=pd.DataFrame(rows)
        variants=pd.DataFrame([dict(gap=1.4,ci_low=1.2,ci_high=1.6,users=3) for _ in range(6)])
        return primary,intervals,variants

    def test_gap_and_support_are_independent_column_size_figures(self):
        from matplotlib.figure import Figure
        snapshots={}
        def capture(fig,path,**kwargs):
            if Path(path).suffix!='.pdf':return
            snapshots[Path(path).stem]=dict(axes=len(fig.axes),size=fig.get_size_inches().copy(),
                x=fig.axes[0].get_xlabel(),y=fig.axes[0].get_ylabel(),
                bars=sum(p.get_height() for p in fig.axes[0].patches),
                tick_font=min(t.get_fontsize() for t in fig.axes[0].get_xticklabels()),
                log=fig.axes[0].get_yscale())
        with tempfile.TemporaryDirectory() as tmp,patch.object(Figure,'savefig',new=capture):
            result=figures.render_frames(Path(tmp),*self.frames(),prefix='observational_')
        self.assertEqual(len(result),8)
        gap=snapshots['observational_gap_distribution'];support=snapshots['observational_event_support']
        self.assertEqual(gap['axes'],1);self.assertEqual(support['axes'],1)
        self.assertLessEqual(gap['size'][0],3.5);self.assertLessEqual(support['size'][0],3.5)
        self.assertEqual(gap['bars'],3);self.assertEqual(gap['x'],'Normalized gap')
        self.assertEqual(support['log'],'log');self.assertGreaterEqual(gap['tick_font'],8)
        self.assertNotIn('observational_gap_support',snapshots)

    def test_exports_preserve_seal_and_reject_in_place_relabeling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=root/'report';report.mkdir()
            for name,frame in zip(['user_scores.csv','intervals.csv','sensitivities.csv'],self.frames()):
                frame.to_csv(report/name,index=False)
            seal(report,['user_scores.csv','intervals.csv','sensitivities.csv'])
            before={p.name:sha256(p) for p in report.iterdir()}
            with self.assertRaises(ValueError):figures.export(report,report/'figures')
            with patch.object(figures,'render_frames',return_value=[]) as render:
                figures.export(report,root/'presentation')
            render.assert_called_once()
            self.assertEqual(before,{p.name:sha256(p) for p in report.iterdir()})
            (report/'user_scores.csv').write_text('altered')
            with patch.object(figures,'render_frames') as render:
                with self.assertRaises(ValueError):figures.export(report,root/'presentation')
            render.assert_not_called()
