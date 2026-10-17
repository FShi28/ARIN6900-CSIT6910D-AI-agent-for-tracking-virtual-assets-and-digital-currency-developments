"""Bounded HTTP fetching with per-hop official-host verification."""

import time
from dataclasses import dataclass
from urllib.parse import urljoin

import requests

from .common import PipelineError, allowed_url, utc_now


class SourceAccessError(PipelineError):
    """Source-wide denial/throttling: a batch must stop, not try more URLs."""


@dataclass(frozen=True)
class Download:
    content: bytes
    downloaded_url: str
    media_type: str
    collected_at: str


class Fetcher:
    def __init__(self, source, log, session=None):
        self.options = source['http']
        self.hosts = source['scope']['allowed_hosts']
        self.log = log
        self.session = session or requests.Session()
        self.session.trust_env = self.options['trust_env']
        self.session.headers.update({'User-Agent': self.options['user_agent'], 'Accept-Encoding': 'identity'})
        self.last_request = None

    def close(self):
        self.session.close()

    def get(self, url, expected_type):
        current = allowed_url(url, self.hosts)
        redirects = 0
        attempts = 0
        while True:
            if self.last_request is not None:
                time.sleep(max(0, self.options['min_interval_seconds'] - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            retry_reason = None
            response = None
            try:
                response = self.session.get(current, timeout=self.options['timeout_seconds'],
                                            allow_redirects=False, stream=True, verify=True)
                status = response.status_code
                if status in (301, 302, 303, 307, 308):
                    if redirects >= self.options['max_redirects'] or not response.headers.get('Location'):
                        raise PipelineError('Invalid or excessive redirects')
                    current = allowed_url(urljoin(current, response.headers['Location']), self.hosts)
                    redirects += 1
                    continue
                # Stop on throttling or denial; do not route around blocking.
                if status in (401, 403, 429):
                    raise SourceAccessError(f'HTTP {status}; source access must be reviewed')
                if status in (500, 502, 503, 504):
                    if response.headers.get('Retry-After'):
                        raise SourceAccessError(f'HTTP {status} requested delayed access; retry on a later run')
                    retry_reason = f'HTTP {status}'
                elif status != 200:
                    raise PipelineError(f'Unexpected HTTP {status}; full response required')
                else:
                    media_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
                    if media_type != expected_type:
                        raise PipelineError(f'Expected {expected_type}, received {media_type or "missing MIME"}')
                    data = bytearray()
                    for block in response.iter_content(chunk_size=65536):
                        data.extend(block)
                        if len(data) > self.options['max_bytes']:
                            raise PipelineError('Response exceeds configured size limit')
                    content = bytes(data)
                    if expected_type == 'application/pdf' and not content.startswith(b'%PDF-'):
                        raise PipelineError('Response is not a PDF despite its MIME type')
                    if expected_type == 'text/html' and b'<html' not in content[:4096].lower():
                        raise PipelineError('Response is not a recognizable HTML document')
                    return Download(content, current, media_type, utc_now())
            except requests.exceptions.SSLError as exc:
                raise PipelineError('TLS verification/connection failed; certificate checks remain enabled') from exc
            except (requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as exc:
                retry_reason = type(exc).__name__
            finally:
                if response is not None:
                    response.close()
            if attempts >= self.options['max_retries']:
                raise PipelineError(f'HTTP retries exhausted: {retry_reason}')
            attempts += 1
            self.log('download', 'retry', current, error_type='HTTPRetry', message=retry_reason, attempt=attempts)
            time.sleep(min(2 ** (attempts - 1), 4))
