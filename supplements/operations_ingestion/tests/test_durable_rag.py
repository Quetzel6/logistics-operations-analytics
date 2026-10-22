import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

from assistant import BriefError
from diagnose_rag_context import load_cases
from durable_rag import CapturedTransport, EvidenceRun
from inspect_rag_run import inspect
from run_rag_durable import execute


class Response(io.BytesIO):
    status = 200


class DurableRagTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / 'run'

    @staticmethod
    def provider(endpoint, payload):
        if endpoint == '/api/embed':
            return {'embeddings': [[1, 0] for _ in payload['input']]}
        return dict(done=True, done_reason='stop', response='{"decision":"insufficient"}')

    def events(self):
        return [json.loads(line) for line in (self.output / 'events.jsonl').read_text().splitlines()]

    def test_interruption_keeps_completed_trial_and_mock_request(self):
        calls = []
        def provider(endpoint, payload):
            calls.append(payload)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return self.provider(endpoint, payload)
        with self.assertRaises(KeyboardInterrupt):
            execute(self.output, 'context', 'qwen2.5:3b', 'nomic-embed-text:v1.5', provider)
        recovered = inspect(self.output)
        self.assertEqual(recovered['state'], 'interrupted')
        self.assertEqual(recovered['completed_observations'], 1)
        self.assertEqual(recovered['observations'][0]['diagnostics']['decision']['raw_generation'], '{"decision":"insufficient"}')
        self.assertEqual(sum(e['event'] == 'mock_request' for e in self.events()), 2)
        self.assertFalse((self.output / 'report.json').exists())

    def test_staged_interruption_keeps_prior_case(self):
        generated = []
        def provider(endpoint, payload):
            if endpoint == '/api/generate':
                if generated:
                    raise KeyboardInterrupt()
                generated.append(True)
            return self.provider(endpoint, payload)
        with self.assertRaises(KeyboardInterrupt):
            execute(self.output, 'staged', 'qwen2.5:3b', 'nomic-embed-text:v1.5', provider)
        recovered = inspect(self.output)
        self.assertEqual(recovered['completed_observations'], 1)
        self.assertEqual(recovered['observations'][0]['case'], 'receiving_window')

    def test_unhandled_failure_is_recorded(self):
        with self.assertRaises(RuntimeError):
            execute(self.output, 'due-date', 'qwen2.5:3b', 'nomic-embed-text:v1.5', Mock(side_effect=RuntimeError()))
        self.assertEqual(inspect(self.output)['state'], 'failed')

    def test_due_date_only_sends_exact_single_record(self):
        provider = Mock(side_effect=self.provider)
        report = execute(self.output, 'due-date', 'qwen2.5:3b', 'nomic-embed-text:v1.5', provider)
        self.assertEqual(report['generation_requests'], 1)
        payload = provider.call_args.args[1]
        inputs = json.loads(payload['prompt'])
        self.assertEqual(inputs['records'], [{'evidence_id': 'order:T204',
            'text': 'Order T204; due_date=2026-12-06; quantity=73.', 'kind': 'order'}])
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(inspect(self.output)['state'], 'completed')
        self.assertFalse(any(e['event'].startswith('http_') for e in self.events()))

    def test_staged_counts_match_always_abstain_frozen_evaluator(self):
        report = execute(self.output, 'staged', 'qwen2.5:3b', 'nomic-embed-text:v1.5', self.provider)
        self.assertEqual((report['case_count'], report['reference_checks_passed'], report['generation_requests']), (16, 8, 15))
        self.assertEqual((report['answerable_passed'], report['answerable_count'], report['model_abstention_passed'], report['model_abstention_count'], report['application_gate_count']), (0, 8, 7, 7, 1))
        self.assertTrue(report['database_unchanged'])
        self.assertEqual(inspect(self.output)['completed_observations'], 16)

    def test_prepared_bytes_saved_before_http_and_response_before_parsing(self):
        raw = b'{"done":true,"response":"invalid-json-model-text","prompt_eval_count":93}'
        with EvidenceRun(self.output, 'test', 'mock_http', 0) as journal:
            def opened(request, timeout):
                recorded = self.events()[-1]
                self.assertEqual(recorded['event'], 'http_request_prepared')
                self.assertEqual(base64.b64decode(recorded['body_base64']), request.data)
                self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/generate')
                self.assertEqual(timeout, 180)
                return Response(raw)
            result = CapturedTransport(journal, Mock(open=opened))('/api/generate', {'prompt': 'วันที่'})
            self.assertEqual(result['prompt_eval_count'], 93)
            self.assertEqual(base64.b64decode(self.events()[-1]['body_base64']), raw)

    def test_invalid_http_json_and_http_error_body_preserved(self):
        with EvidenceRun(self.output, 'test', 'mock_http', 0) as journal:
            with self.assertRaisesRegex(BriefError, 'local_invalid_json'):
                CapturedTransport(journal, Mock(open=Mock(return_value=Response(b'not-json'))))('/api/generate', {})
            self.assertEqual(base64.b64decode(self.events()[-1]['body_base64']), b'not-json')
            error = urllib.error.HTTPError('http://127.0.0.1:11434/api/show', 404, 'missing', {}, io.BytesIO(b'{"error":"missing model"}'))
            with self.assertRaisesRegex(BriefError, 'local_provider_http_404'):
                CapturedTransport(journal, Mock(open=Mock(side_effect=error)))('/api/show', {})
            self.assertEqual(self.events()[-1]['status'], 404)

    def test_no_http_dispatch_if_request_journal_write_fails(self):
        journal, opener = Mock(), Mock()
        journal.event.side_effect = OSError('disk full')
        with self.assertRaises(OSError):
            CapturedTransport(journal, opener)('/api/generate', {})
        opener.open.assert_not_called()

    def test_metadata_keeps_full_digest_template_and_missing_identity_stops(self):
        with EvidenceRun(self.output, 'test', 'mock_http', 0) as journal:
            call = CapturedTransport(journal, Mock())
            call.request = Mock(side_effect=[{'version': 'test'},
                {'models': [{'name': 'qwen2.5:3b', 'digest': 'a' * 64}]},
                {'template': 'SYSTEM={{ .System }}', 'parameters': 'num_ctx 2048'}])
            metadata = call.metadata(['qwen2.5:3b'])
            self.assertEqual(metadata['models']['qwen2.5:3b']['digest'], 'a' * 64)
            self.assertIn('template', metadata['models']['qwen2.5:3b']['show'])
            call.request = Mock(side_effect=[{'version': 'test'}, {'models': []}])
            with self.assertRaisesRegex(BriefError, 'model_identity_unavailable'):
                call.metadata(['qwen2.5:3b'])
            self.assertEqual(call.request.call_count, 2)

    def test_old_outputs_never_overwritten_and_frozen_sources_still_validate(self):
        execute(self.output, 'due-date', 'qwen2.5:3b', 'nomic-embed-text:v1.5', self.provider)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        provider = Mock()
        with self.assertRaises(FileExistsError):
            execute(self.output, 'due-date', 'qwen2.5:3b', 'nomic-embed-text:v1.5', provider)
        provider.assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})
        load_cases()

    def test_live_path_preflights_and_checks_identity_with_simulated_http(self):
        # HTTP is simulated: the production live path is tested, not model behavior.
        import run_rag_durable
        inventory = {'models': [{'name': 'qwen2.5:3b', 'digest': 'a' * 64}]}
        payloads = []
        def opened(request, timeout):
            payloads.append((request.full_url, request.data))
            endpoint = request.full_url.rsplit('/', 1)[-1]
            result = {'version': 'test'} if endpoint == 'version' else (
                inventory if endpoint == 'tags' else {'template': 'test'} if endpoint == 'show' else
                self.provider('/api/generate', {}) if endpoint == 'generate' else {'models': []})
            return Response(json.dumps(result).encode())
        with patch.object(run_rag_durable, 'CapturedTransport',
                          side_effect=lambda journal: CapturedTransport(journal, Mock(open=opened))):
            report = execute(self.output, 'due-date', 'qwen2.5:3b', 'nomic-embed-text:v1.5')
        self.assertTrue(report['model_identity_unchanged'])
        self.assertEqual([url.rsplit('/', 1)[-1] for url, _ in payloads],
                         ['version', 'tags', 'show', 'generate', 'ps', 'tags'])
        self.assertEqual(sum(e['event'] == 'http_response' for e in self.events()), 6)

    def test_identity_drift_fails_but_keeps_completed_report(self):
        import run_rag_durable
        tag_reads = []
        def opened(request, timeout):
            endpoint = request.full_url.rsplit('/', 1)[-1]
            if endpoint == 'tags':
                tag_reads.append(True)
                result = {'models': [{'name': 'qwen2.5:3b', 'digest': ('a' if len(tag_reads) == 1 else 'b') * 64}]}
            elif endpoint == 'generate':
                result = self.provider('/api/generate', {})
            else:
                result = {'version': 'test'} if endpoint == 'version' else {'template': 'test'}
            return Response(json.dumps(result).encode())
        with patch.object(run_rag_durable, 'CapturedTransport',
                          side_effect=lambda journal: CapturedTransport(journal, Mock(open=opened))):
            with self.assertRaisesRegex(BriefError, 'runtime_model_identity_changed'):
                execute(self.output, 'due-date', 'qwen2.5:3b', 'nomic-embed-text:v1.5')
        self.assertEqual(inspect(self.output)['state'], 'failed')
        self.assertEqual(inspect(self.output)['completed_observations'], 1)
        self.assertFalse(json.loads((self.output / 'report.json').read_text())['model_identity_unchanged'])

    @unittest.skipUnless(os.name == 'posix', 'SIGTERM requires POSIX')
    def test_cli_sigterm_preserves_trial_and_returns_130(self):
        program = '''import os,signal,sys
import run_rag_durable as runner
original = runner.execute
calls = []
def provider(endpoint, payload):
    if calls:
        os.kill(os.getpid(), signal.SIGTERM)
    calls.append(True)
    return dict(done=True, done_reason='stop', response='{"decision":"supported"}')
runner.execute = lambda directory, mode, model, embed: original(directory, mode, model, embed, provider)
sys.argv = ['run_rag_durable.py', '--protocol', 'context', '--allow-local', '--output', sys.argv[1]]
raise SystemExit(runner.main())
'''
        result = subprocess.run([sys.executable, '-c', program, str(self.output)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True)
        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertEqual(inspect(self.output)['state'], 'interrupted')
        self.assertEqual(inspect(self.output)['completed_observations'], 1)

    @unittest.skipUnless(os.name == 'posix', 'SIGKILL requires POSIX')
    def test_sigkill_keeps_completed_observation_without_finish_event(self):
        program = ('import os,signal,sys\nfrom durable_rag import EvidenceRun\n'
                   'with EvidenceRun(sys.argv[1],"kill-test","mock_only",2) as run:\n'
                   ' run.observation({"outcome":"supported"})\n'
                   ' os.kill(os.getpid(),signal.SIGKILL)\n')
        process = subprocess.run([sys.executable, '-c', program, str(self.output)],
                                 cwd=Path(__file__).resolve().parents[1], capture_output=True)
        self.assertEqual(process.returncode, -9)
        recovered = inspect(self.output)
        self.assertEqual((recovered['state'], recovered['completed_observations']), ('incomplete', 1))
        with (self.output / 'events.jsonl').open('ab') as file:
            file.write(b'{"sequence":')
        self.assertTrue(inspect(self.output)['partial_tail'])
        self.assertEqual(inspect(self.output)['completed_observations'], 1)

    def test_interior_corruption_is_not_hidden(self):
        with EvidenceRun(self.output, 'test', 'mock_only', 0):
            pass
        with (self.output / 'events.jsonl').open('ab') as file:
            file.write(b'not-json\n')
        with self.assertRaises(ValueError):
            inspect(self.output)
