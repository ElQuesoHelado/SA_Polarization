"""Guard user edits and restrict verified GPU integration to its result block."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from polarization_pipeline.targeted.common import atomic_json, sha256
from polarization_pipeline.targeted.publication import observational_manuscript as document
from polarization_pipeline.targeted.publication.state import seal

class ManuscriptGuardTests(unittest.TestCase):
    def fixture(self, root):
        (root/'docs').mkdir();source=root/'docs/doc_a_modificar.tex'
        text='Original author paragraph.\n'+document.BEGIN+'\nOld models\n'+document.END+'\nObservational result stays.'
        source.write_text(text)
        report=root/'report';report.mkdir();rows=[]
        for m in document.NAMES:
            for panel in ['end_to_end','common_complete_candidates']:
                rows.append(dict(model_id=m,panel=panel,macro_f1=.4,coverage=.2,pairs=20))
        pd.DataFrame(rows).to_csv(report/'comparison.csv',index=False)
        ci=pd.DataFrame([dict(model_id=m,metric='macro_f1',estimate=.4,ci_low=.3,ci_high=.5,status='estimated') for m in document.NAMES])
        ci.to_csv(report/'intervals.csv',index=False)
        pd.DataFrame([dict(left='beto',right='mrbert_es',p_holm=.8)]).to_csv(report/'model_contrasts.csv',index=False)
        seal(report,['comparison.csv','intervals.csv','model_contrasts.csv'])
        statistics=report.parent/'manuscript_statistics';statistics.mkdir()
        ci.to_csv(statistics/'common_context_intervals.csv',index=False)
        seal(statistics,['common_context_intervals.csv'],comparison_sha256=sha256(report/'manifest.json'))
        control=root/'control';control.mkdir()
        atomic_json(control/'observational_manuscript_guard.json',dict(root=str(root),sources={'docs/doc_a_modificar.tex':sha256(source)},output=str(root/'outputs')))
        return source,report,control,text

    def test_missing_guard_never_edits_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,report,control,text=self.fixture(root)
            (control/'observational_manuscript_guard.json').unlink()
            self.assertEqual(document.refresh_models(report,control),'pending_observational_manuscript')
            self.assertEqual(source.read_text(),text)

    def test_user_edits_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,report,control,_=self.fixture(Path(tmp));source.write_text('User changed this')
            with patch.object(document.subprocess,'run') as compile_pdf:
                self.assertEqual(document.refresh_models(report,control),'pending_source_changed')
            compile_pdf.assert_not_called();self.assertEqual(source.read_text(),'User changed this')

    def test_verified_comparison_changes_only_model_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,report,control,text=self.fixture(Path(tmp))
            def compile_pdf(args,**kwargs):
                target=Path(next(x.split('=',1)[1] for x in args if x.startswith('-outdir=')))
                target.mkdir();(target/'doc_a_modificar.pdf').write_bytes(b'synthetic test PDF')
            with patch.object(document.subprocess,'run',side_effect=compile_pdf):
                path=document.refresh_models(report,control)
            result=source.read_text()
            self.assertTrue(Path(path).exists());self.assertIn('mDeBERTa-v3-base',result)
            self.assertIn('End-to-end evaluation',result)
            table=result.split(r'\begin{table*}')[1].split(r'\end{table*}')[0]
            self.assertNotIn('Coverage',table)
            self.assertIn('95\\% CI',table)
            self.assertEqual(result.count('Accepted predictions cover'),1)
            self.assertIn('Table~',result)
            self.assertIn('compared five models',result)
            self.assertIn('Accepted predictions covered',result)
            self.assertNotIn('Model differences combinedd',result)
            self.assertNotIn('the supplement reports',result)
            self.assertNotIn('Evaluación integral',result)
            self.assertEqual(result.split(document.BEGIN)[0],text.split(document.BEGIN)[0])
            self.assertEqual(result.split(document.END)[1],text.split(document.END)[1])
            self.assertEqual(result.count(document.BEGIN),1)

    def test_failed_compile_rolls_back_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,report,control,text=self.fixture(root)
            with patch.object(document.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'latexmk')):
                with self.assertRaises(subprocess.CalledProcessError):document.refresh_models(report,control)
            self.assertEqual(source.read_text(),text)
            self.assertEqual(len(list((root/'outputs').glob('*/antes.tex'))),1)

    def test_tampered_comparison_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,report,control,text=self.fixture(Path(tmp));(report/'comparison.csv').write_text('altered')
            with self.assertRaises(ValueError):document.refresh_models(report,control)
            self.assertEqual(source.read_text(),text)

    def test_incomplete_or_invalid_metrics_never_enter_manuscript(self):
        for kind in ['missing_model','invalid_metric','different_denominator']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                source,report,control,text=self.fixture(Path(tmp))
                frame=pd.read_csv(report/'comparison.csv')
                if kind=='missing_model':frame=frame[frame.model_id.ne('mrbert_es')]
                elif kind=='invalid_metric':frame.loc[0,'coverage']=1.2
                else:frame.loc[0,'pairs']=99
                frame.to_csv(report/'comparison.csv',index=False);seal(report,['comparison.csv','intervals.csv','model_contrasts.csv'])
                stats=report.parent/'manuscript_statistics'
                seal(stats,['common_context_intervals.csv'],comparison_sha256=sha256(report/'manifest.json'))
                with self.assertRaises(ValueError):document.refresh_models(report,control)
                self.assertEqual(source.read_text(),text)

    def test_missing_or_altered_intervals_never_enter_document(self):
        for kind in ['missing','invalid','wrong_estimate','altered_derivative']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                source,report,control,text=self.fixture(Path(tmp))
                ci=pd.read_csv(report/'intervals.csv')
                if kind=='missing': ci=ci.iloc[1:]
                elif kind=='invalid': ci.loc[0,'ci_high']=1.5
                elif kind=='wrong_estimate': ci.loc[0,'estimate']=.6
                if kind=='altered_derivative':
                    (report.parent/'manuscript_statistics/common_context_intervals.csv').write_text('altered')
                else:
                    ci.to_csv(report/'intervals.csv',index=False)
                    seal(report,['comparison.csv','intervals.csv','model_contrasts.csv'])
                    stats=report.parent/'manuscript_statistics'
                    seal(stats,['common_context_intervals.csv'],comparison_sha256=sha256(report/'manifest.json'))
                with self.assertRaises(ValueError): document.refresh_models(report,control)
                self.assertEqual(source.read_text(),text)
