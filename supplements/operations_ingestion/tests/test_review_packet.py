import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from review_packet import generate,score
class ReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'review'
        with patch('assistant.generate_selection',side_effect=AssertionError('remote forbidden')):
            self.result=generate(self.path)
    def test_required_evidence_present_but_human_review_pending(self):
        self.assertEqual(self.result['missing_required_evidence_cases'],0)
        self.assertEqual(score(self.path)['pending_cases'],8)
        self.assertEqual(score(self.path)['passed_cases'],0)
    def test_cannot_overwrite_decisions(self):
        before=(self.path/'decisions.json').read_bytes()
        with self.assertRaises(FileExistsError):generate(self.path)
        self.assertEqual(before,(self.path/'decisions.json').read_bytes())
    def test_tampered_packet_rejected(self):
        p=self.path/'packet.json';p.write_text(p.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'packet_changed'):score(self.path)
    def test_rating_needs_rationale_and_reviewer(self):
        p=self.path/'decisions.json';d=json.loads(p.read_text())
        for item in d['cases'][0].values():
            if isinstance(item,dict):item['rating']='pass'
        p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'rationale_required'):score(self.path)
        for item in d['cases'][0].values():
            if isinstance(item,dict):item['rationale']='Reviewer checked source.'
        p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'reviewer_required'):score(self.path)
        d['reviewer']='Test reviewer';p.write_text(json.dumps(d))
        self.assertEqual(score(self.path)['passed_cases'],1)
