import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from context_selector import select_context
from evaluate_rag_challenge import CASES
from evaluate_rag_ids_v2 import NEW_CASES
from prospective_dataset import DATA, build, validate_lock, verify
import prospective_dataset


class ProspectiveDatasetTests(unittest.TestCase):
    def test_frozen_data_schema_and_references_validate_without_provider(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network forbidden')):
            result = verify()
        self.assertEqual((result['cases'], result['answerable'], result['model_abstention_cases'], result['application_gate_cases']), (16, 8, 7, 1))
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(result['human_reference_review'], 'pending')

    def test_questions_and_ids_new_while_runtime_remains_frozen(self):
        lock = validate_lock()
        self.assertEqual(lock['candidate_freeze_commit'], 'b9714367510bdd5f3175b2f3c2642d87364e6a3d')
        cases = json.loads((DATA / 'cases.json').read_text())
        self.assertFalse({c['question'] for c in cases} & {c[2] for c in CASES + NEW_CASES})
        self.assertFalse({c['order_id'] for c in cases} & {c[1] for c in CASES + NEW_CASES})
        evidence = [dict(evidence_id='new-order', kind='order', text='synthetic')]
        routed = [c['case'] for c in cases if select_context(c['question'], evidence, ['new-order'])['route'] != 'fallback']
        self.assertEqual(routed, ['P01', 'P03'])

    def test_builder_never_overwrites_existing_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'bundle'
            build(root)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with self.assertRaises(FileExistsError):
                build(root)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_data_and_frozen_runtime_drift_are_rejected(self):
        lock = validate_lock()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / 'data'
            data.mkdir()
            for name in ('manifest.json', 'bundle.json', 'cases.json'):
                (data / name).write_bytes((DATA / name).read_bytes())
            for name in lock['frozen_runtime_sha256']:
                (root / name).write_bytes((prospective_dataset.ROOT / name).read_bytes())
            with patch.object(prospective_dataset, 'ROOT', root), patch.object(prospective_dataset, 'DATA', data):
                (root / 'context_selector.py').write_text('changed candidate')
                with self.assertRaisesRegex(ValueError, 'frozen_candidate_changed'):
                    validate_lock()
                (root / 'context_selector.py').write_bytes((DATA.parent / 'context_selector.py').read_bytes())
                (data / 'cases.json').write_text('[]')
                with self.assertRaisesRegex(ValueError, 'prospective_data_changed'):
                    validate_lock()
