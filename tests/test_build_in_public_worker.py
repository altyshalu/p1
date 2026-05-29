from urllib.error import HTTPError

import pytest

from l2l3_protocol.workers import build_in_public_worker
from l2l3_protocol.workers.build_in_public_worker import WorkerInputError, adapt


def test_channel_adapter_accepts_real_hermes_atom_shape() -> None:
    result = adapt(
        {
            'inputs': {
                'atoms': [
                    {
                        'headline': 'Implemented evidence-backed review CLI',
                        'body': 'This allows checking claims against data directly from the terminal.',
                        'type': 'feature_update',
                    }
                ],
                'channels': ['x'],
            }
        },
        {},
    )

    assert result['drafts'][0]['channel'] == 'x'
    assert 'Implemented evidence-backed review CLI' in result['drafts'][0]['text']
    assert 'Why it matters' in result['drafts'][0]['text']
    assert result['drafts'][0]['source_angle'] == 'feature_update'


def test_channel_adapter_accepts_string_atoms() -> None:
    result = adapt(
        {
            'inputs': {
                'atoms': ['Implemented evidence-backed review CLI from the terminal.'],
                'channels': ['x'],
            }
        },
        {},
    )

    assert result['drafts'][0]['text'] == 'Implemented evidence-backed review CLI from the terminal.'
    assert result['drafts'][0]['source_angle'] == 'generic'


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_real_request_layer_retries_rate_limits_without_traceback(monkeypatch) -> None:
    calls = 0

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(request.full_url, 429, 'Too Many Requests', {}, None)
        return _Response(b'<feed></feed>')

    monkeypatch.setattr(build_in_public_worker, 'urlopen', fake_urlopen)
    monkeypatch.setattr(build_in_public_worker.time, 'sleep', lambda _seconds: None)

    assert build_in_public_worker._request_text('https://export.arxiv.org/api/query?x=1') == '<feed></feed>'
    assert calls == 2


def test_real_request_layer_surfaces_persistent_rate_limit_as_worker_input_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 429, 'Too Many Requests', {}, None)

    monkeypatch.setattr(build_in_public_worker, 'urlopen', fake_urlopen)
    monkeypatch.setattr(build_in_public_worker.time, 'sleep', lambda _seconds: None)

    with pytest.raises(WorkerInputError, match='status 429'):
        build_in_public_worker._request_text('https://export.arxiv.org/api/query?x=1')


def test_real_request_layer_surfaces_persistent_timeout_as_worker_input_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise TimeoutError('read operation timed out')

    monkeypatch.setattr(build_in_public_worker, 'urlopen', fake_urlopen)
    monkeypatch.setattr(build_in_public_worker.time, 'sleep', lambda _seconds: None)

    with pytest.raises(WorkerInputError, match='timed out'):
        build_in_public_worker._request_text('https://export.arxiv.org/api/query?x=1')
