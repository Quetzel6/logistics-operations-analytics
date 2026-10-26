"""Simulated HTTP only; these tests do not establish model behavior."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from assistant import BriefError
from durable_rag import CapturedTransport
from diagnose_rag_format import execute, load_capture
from inspect_rag_run import inspect
import run_rag_durable


class Response(io.BytesIO):
    status = 200


class FormatDiagnosticTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.baseline = self.root / 'baseline'
        self.output = self.root / 'no-format'
        self.calls = []
        self.version = 'test'
        self.model_digest = 'a' * 64
        self.template = 'test-template'
        self.generation = dict(done=True, done_reason='stop', response='{"decision":"insufficient"}')
        with patch.object(run_rag_durable, 'CapturedTransport', side_effect=self.factory):
            run_rag_durable.execute(self.baseline, 'due-date', 'qwen2.5:3b', 'nomic-embed-text:v1.5')
        self.calls.clear()
        self.baseline_bytes = {p.name: p.read_bytes() for p in self.baseline.iterdir()}

    def opened(self, request, timeout):
        endpoint = request.full_url.rsplit('/', 1)[-1]
        payload = json.loads(request.data) if request.data else None
        self.calls.append((endpoint, payload))
        result = ({'version': self.version} if endpoint == 'version' else
                  {'models': [{'name': 'qwen2.5:3b', 'digest': self.model_digest}]} if endpoint == 'tags' else
                  {'template': self.template} if endpoint == 'show' else
                  self.generation if endpoint == 'generate' else {'models': []})
        if isinstance(result, BaseException):
            raise result
        return Response(json.dumps(result).encode())

    def factory(self, journal):
        return CapturedTransport(journal, Mock(open=self.opened))

    def invoke(self):
        return execute(self.output, self.baseline, True, self.factory)

    def test_only_format_removed_with_one_generation_and_baseline_preserved(self):
        expected = load_capture(self.baseline)['payload']
        report = self.invoke()
        generated = [payload for endpoint, payload in self.calls if endpoint == 'generate']
        self.assertEqual(generated, [{k: v for k, v in expected.items() if k != 'format'}])
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(report['generation_requests'], 1)
        self.assertEqual(report['trials'][0]['outcome'], 'insufficient')
        self.assertEqual(inspect(self.output)['state'], 'completed')
        self.assertEqual(self.baseline_bytes, {p.name: p.read_bytes() for p in self.baseline.iterdir()})

    def test_prose_retained_and_not_repaired_into_supported(self):
        self.generation['response'] = 'The due date is 2026-12-06.'
        report = self.invoke()
        trial = report['trials'][0]
        self.assertEqual(trial['outcome'], 'failed')
        self.assertEqual(trial['diagnostics']['decision']['raw_generation'], self.generation['response'])
        self.assertIn('not automatically semantically wrong', trial['semantic_review'])
        self.assertEqual(inspect(self.output)['completed_observations'], 1)

    def test_version_digest_and_template_changes_stop_before_generation(self):
        for attribute, changed in [('version', 'changed'), ('model_digest', 'b' * 64), ('template', 'changed')]:
            with self.subTest(attribute=attribute):
                old = getattr(self, attribute)
                self.output = self.root / attribute
                self.calls.clear()
                setattr(self, attribute, changed)
                with self.assertRaises(ValueError):
                    self.invoke()
                self.assertFalse(any(endpoint == 'generate' for endpoint, _ in self.calls))
                self.assertEqual(inspect(self.output)['state'], 'failed')
                setattr(self, attribute, old)

    def test_opt_in_and_new_directory_required(self):
        with self.assertRaisesRegex(BriefError, 'local_inference_disabled'):
            execute(self.output, self.baseline, transport_factory=self.factory)
        self.assertFalse(self.output.exists())
        self.invoke()
        self.calls.clear()
        with self.assertRaises(FileExistsError):
            self.invoke()
        self.assertEqual(self.calls, [])

    def test_corrupt_baseline_rejected_before_provider(self):
        p = self.baseline / 'events.jsonl'
        rows = [json.loads(line) for line in p.read_text().splitlines()]
        next(e for e in rows if e['event'] == 'http_response')['body_sha256'] = 'bad'
        p.write_text(''.join(json.dumps(e) + '\n' for e in rows))
        with self.assertRaisesRegex(ValueError, 'baseline_body_hash_mismatch'):
            self.invoke()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.output.exists())

    def test_interruption_keeps_prepared_request_and_marks_state(self):
        self.generation = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.invoke()
        self.assertEqual(inspect(self.output)['state'], 'interrupted')
        self.assertEqual(len([p for e, p in self.calls if e == 'generate']), 1)
