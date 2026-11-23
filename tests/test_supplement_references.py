"""Generated tables remain referenced even when optional sections change order."""
import importlib.util
from pathlib import Path
import re
import unittest

spec = importlib.util.spec_from_file_location('supplement_export',
    Path(__file__).resolve().parents[1]/'scripts/build_observational_supplement.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


class SupplementReferenceTests(unittest.TestCase):
    def test_each_registered_table_has_a_stable_label_and_prose_call(self):
        labels=[]
        for caption in export.TABLE_CONTEXT:
            result=export.table(caption,['Metric','Value'],[['Example','1']])
            label=re.findall(r'\\label\{([^}]+)\}',result)
            self.assertEqual(len(label),1)
            self.assertEqual(re.findall(r'\\ref\{([^}]+)\}',result),label)
            self.assertLess(result.index(r'\ref'),result.index(r'\begin{table}'))
            self.assertEqual(result,export.table(caption,['Metric','Value'],[['Example','1']]))
            labels.extend(label)
        self.assertEqual(len(labels),len(set(labels)))

    def test_new_tables_require_an_explanatory_reference(self):
        with self.assertRaisesRegex(ValueError,'explanatory reference'):
            export.table('Unregistered result',['Metric'],[['Example']])
