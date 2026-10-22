"""Durable journals and client-side HTTP body capture for synthetic experiments."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import urllib.error
import urllib.request

from assistant import BriefError, NoRedirect
from local_rag import BASE_URL


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write('\n')
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


class EvidenceRun:
    """New directories only. JSONL is authoritative if the process dies abruptly."""

    def __init__(self, directory, protocol, execution, planned):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.state = dict(protocol=protocol, execution=execution, state='running',
                          started_utc=now(), planned_observations=planned,
                          completed_observations=0, python=platform.python_version(),
                          platform=platform.platform())
        self.sequence = 0
        self.scope = {}
        self.event('run_started', **self.state)
        atomic_json(self.directory / 'status.json', self.state)

    def event(self, event, **fields):
        self.sequence += 1
        row = dict(sequence=self.sequence, timestamp_utc=now(), event=event,
                   scope=dict(self.scope), **fields)
        # Flush every event before continuing, especially before dispatching HTTP.
        with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as file:
            file.write(json.dumps(row, ensure_ascii=False) + '\n')
            file.flush()
            os.fsync(file.fileno())
        return self.sequence

    def observation(self, row):
        self.event('observation', observation=row)
        self.state['completed_observations'] += 1
        atomic_json(self.directory / 'status.json', self.state)

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        state = 'completed' if kind is None else (
            'interrupted' if issubclass(kind, (KeyboardInterrupt, SystemExit)) else 'failed')
        self.state.update(state=state, finished_utc=now())
        if error is not None:
            self.state['error_type'] = type(error).__name__
        self.event('run_finished', **self.state)
        atomic_json(self.directory / 'status.json', self.state)
        return False


class CapturedTransport:
    """Captures exact client HTTP bodies, not TCP packets or rendered model input.

    Construction never contacts Ollama. A custom opener is for HTTP-level tests.
    """

    def __init__(self, journal, opener=None, base_url=BASE_URL):
        self.journal = journal
        self.base_url = base_url
        self.opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, endpoint, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base_url + endpoint, data=body,
            headers={'Content-Type': 'application/json'},
            method='GET' if body is None else 'POST')
        request_id = self.journal.event(
            'http_request_prepared', capture_scope='client_http_body',
            method=request.method, url=request.full_url,
            headers=dict(request.header_items()),
            body_base64=None if body is None else base64.b64encode(body).decode(),
            body_sha256=None if body is None else hashlib.sha256(body).hexdigest())
        # Prepared does not imply delivery; a response is recorded separately.
        try:
            try:
                response = self.opener.open(request, timeout=180)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                raw = response.read(2_000_001)
                self.journal.event('http_response', request_id=request_id,
                                   status=response.status,
                                   body_base64=base64.b64encode(raw).decode(),
                                   body_sha256=hashlib.sha256(raw).hexdigest(),
                                   truncated=len(raw) > 2_000_000)
                status = response.status
        except BaseException as error:
            self.journal.event('http_error', request_id=request_id,
                               error_type=type(error).__name__)
            if isinstance(error, (urllib.error.URLError, OSError, TimeoutError)):
                raise BriefError('local_provider_unavailable') from None
            raise
        if len(raw) > 2_000_000:
            raise BriefError('local_response_too_large')
        if not 200 <= status < 300:
            raise BriefError('local_provider_http_' + str(status))
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise BriefError('local_invalid_json') from None
        if not isinstance(result, dict) or 'error' in result:
            raise BriefError('local_provider_error')
        return result

    def __call__(self, endpoint, payload):
        return self.request(endpoint, payload)

    def metadata(self, models):
        version = self.request('/api/version')
        inventory = self.request('/api/tags')
        details = {}
        for model in dict.fromkeys(models):
            # No /api/pull: missing models stop this experiment.
            matches = [m for m in inventory.get('models', [])
                       if m.get('name') == model or m.get('model') == model]
            if len(matches) != 1 or not re.fullmatch(
                    r'(?:sha256:)?[0-9a-f]{64}', matches[0].get('digest', '')):
                raise BriefError('model_identity_unavailable:' + model)
            details[model] = dict(digest=matches[0]['digest'],
                                 show=self.request('/api/show', {'model': model}))
        result = dict(version=version, inventory=inventory, models=details,
                      effective_runtime_defaults='Not fully observable; inspect template, parameters and /api/ps alongside configured options.')
        atomic_json(self.journal.directory / 'runtime.json', result)
        self.journal.event('runtime_metadata', metadata=result)
        return result
