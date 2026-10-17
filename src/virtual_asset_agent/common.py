"""Small shared identity, time and local file helpers."""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class PipelineError(ValueError):
    """Expected input, source or quality failure."""


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def identity(*parts):
    return sha256(json_bytes(list(parts)))


def canonical_url(url):
    try:
        parts = urlsplit(url)
        port = parts.port
    except (ValueError, TypeError) as exc:
        raise PipelineError('Malformed URL') from exc
    if (parts.scheme.lower() != 'https' or not parts.hostname or parts.username
            or parts.password or port not in (None, 443) or any(c.isspace() for c in url)):
        raise PipelineError('Expected an HTTPS URL without credentials or nonstandard port')
    return urlunsplit(('https', parts.hostname.lower(), parts.path, parts.query, ''))


def allowed_url(url, hosts):
    result = canonical_url(url)
    if urlsplit(result).hostname not in hosts:
        raise PipelineError('URL host is outside the configured official source')
    return result


def local_path(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    path = (root / relative).resolve()
    if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(root):
        raise PipelineError('Expected a safe workspace-relative path')
    return path


def write_immutable(path, data):
    """Publish a complete file without ever replacing an existing destination."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise PipelineError(f'Immutable file content mismatch: {path.name}')
        return
    descriptor, temporary = tempfile.mkstemp(prefix='.ingestion-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise PipelineError(f'Immutable file content mismatch: {path.name}')
    finally:
        Path(temporary).unlink(missing_ok=True)
