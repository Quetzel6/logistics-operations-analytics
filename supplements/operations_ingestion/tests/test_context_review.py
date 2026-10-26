"""All capture/model behavior here is simulated; no human ratings are fabricated."""
import json
from unittest.mock import patch
import unittest
import zipfile

import test_context_comparison as fixture_module
from evaluate_context_selector import execute
from replay_context_selector import replay
from review_context_selector import generate, score, RUBRIC


class ContextReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.ContextComparisonTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        f.support_all = True
        with patch('evaluate_context_selector.CapturedTransport', side_effect=f.fixture.factory):
            execute(f.output, f.baseline, True)
        self.archive = f.fixture.root / 'capture.zip'
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for file in f.output.iterdir():
                archive.write(file, 'evidence/capture/' + file.name)
        self.output = f.fixture.root / 'review'

    def test_review_packet_has_pending_ratings_and_no_reference_scores(self):
        before = self.archive.read_bytes()
        result = generate(self.archive, self.output)
        self.assertEqual(result, dict(unit_count=32, human_review_status='pending', model_calls=0))
        packet = json.loads((self.output / 'packet.json').read_text())
        for unit in packet['units']:
            self.assertFalse(set(unit) & {'required_ids', 'expected_status', 'checks', 'arm', 'case'})
        rated = score(self.output)
        self.assertEqual((rated['pending'], rated['human_review_status']), (32, 'pending'))
        self.assertEqual(before, self.archive.read_bytes())
        decisions = (self.output / 'decisions.json').read_bytes()
        with self.assertRaises(FileExistsError):
            generate(self.archive, self.output)
        self.assertEqual(decisions, (self.output / 'decisions.json').read_bytes())

    def test_ai_review_never_completes_human_review(self):
        generate(self.archive, self.output)
        path = self.output / 'decisions.json'
        decisions = json.loads(path.read_text())
        decisions.update(reviewer='synthetic-test-reviewer', reviewer_kind='ai')
        for unit in decisions['units']:
            for name in RUBRIC:
                unit[name] = dict(rating='pass', rationale='Synthetic test only; not a real rating.')
        path.write_text(json.dumps(decisions))
        result = score(self.output)
        self.assertEqual((result['passed'], result['review_status']), (32, 'completed'))
        self.assertEqual(result['human_review_status'], 'pending')

    def test_identity_rationale_and_not_applicable_validation(self):
        generate(self.archive, self.output)
        path = self.output / 'decisions.json'
        d = json.loads(path.read_text())
        d['units'][0]['answerability'] = dict(rating='fail', rationale='Test reason')
        path.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, 'reviewer_and_kind_required'):
            score(self.output)
        d.update(reviewer='test', reviewer_kind='human')
        d['units'][0]['answerability']['rationale'] = ''
        path.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, 'rationale_required'):
            score(self.output)
        d['units'][0]['answerability'] = dict(rating='not_applicable', rationale='test')
        path.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, 'not_applicable_requires'):
            score(self.output)

    def test_packet_tampering_is_rejected(self):
        generate(self.archive, self.output)
        path = self.output / 'packet.json'
        path.write_text(path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'packet_changed'):
            score(self.output)

    def test_html_escapes_untrusted_source_content(self):
        from review_context_selector import read_capture
        report, hashes = read_capture(self.archive)
        report['cases'][0]['question'] = '<script>untrusted()</script>'
        with patch('review_context_selector.read_capture', return_value=(report, hashes)):
            generate(self.archive, self.output)
        page = (self.output / 'review.html').read_text()
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)

    def test_offline_replay_reproduces_capture_without_network(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network forbidden')):
            result = replay(self.archive, self.fixture.fixture.root / 'replay')
        self.assertEqual(result['live_model_calls'], 0)
        self.assertEqual(result['independent_new_observations'], 0)
        self.assertEqual(result['replayed_inference_requests'], 75)
