"""Stateful client + module-level convenience wrappers.

The ``Client`` object encapsulates a base URL and a bearer token. The
module-level ``authenticate()`` / ``run()`` functions operate on a
shared default client so short scripts stay one-liners.
"""
from __future__ import annotations

import io
import os
import time
import zipfile
from pathlib import Path
from typing import Optional

import requests


DEFAULT_BASE_URL = os.getenv(
    'PIVOTALJREPORT_BASE_URL',
    'https://apps2.pivotalpath.com/jreport',
)
DEFAULT_POLL_INTERVAL = 3.0       # seconds
DEFAULT_TIMEOUT = 30 * 60         # 30 minutes


class AuthError(RuntimeError):
    """Login failed or token expired."""


class JobError(RuntimeError):
    """Job reached a failed or partial terminal state."""


# --- Client ------------------------------------------------------------

class Client:
    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.token = token

    # ---- auth ----
    def authenticate(self, username: str, password: str) -> dict:
        r = requests.post(
            f'{self.base_url}/sdk/v1/login',
            json={'username': username, 'password': password},
            timeout=30,
        )
        if r.status_code != 200:
            try:
                msg = r.json().get('error', r.text)
            except Exception:
                msg = r.text
            raise AuthError(f'login failed: {msg}')
        body = r.json()
        self.token = body['token']
        return body

    def _auth_headers(self) -> dict:
        if not self.token:
            raise AuthError('not authenticated — call authenticate() first')
        return {'Authorization': f'Bearer {self.token}'}

    # ---- high-level flow ----
    def run(self, folder: Optional[str] = None,
            out: Optional[str] = None,
            batch_tag: Optional[str] = None,
            poll_interval: float = DEFAULT_POLL_INTERVAL,
            timeout: float = DEFAULT_TIMEOUT,
            verbose: bool = True) -> dict:
        """Zip ``folder``, upload, poll, extract PDFs into ``out``.

        ``folder`` defaults to the current working directory.
        ``out``    defaults to ``<cwd>/<server-chosen-tag>``, matching the
        label the archive shows for this batch; collision-suffixed if the
        target already exists.
        """
        folder_path = Path(folder) if folder else Path.cwd()
        folder_path = folder_path.resolve()
        if not folder_path.is_dir():
            raise FileNotFoundError(f'folder not found: {folder_path}')

        zip_bytes, n = _zip_xlsx_folder(folder_path)
        if n == 0:
            raise ValueError(f'no .xlsx files in {folder_path}')

        if verbose:
            print(f'[pivotaljreport] uploading {n} file(s) from {folder_path}')
        job = self._upload(zip_bytes, folder_path.name, batch_tag)
        job_id = job['job_id']
        tag = job.get('tag') or f'job-{job_id}'
        if verbose:
            print(f'[pivotaljreport] job {job_id} queued (tag={tag!r})')

        if out is None:
            out_path = _uniquify_dir(Path.cwd() / _sanitize_name(tag))
        else:
            out_path = Path(out).resolve()

        status = self._poll_until_done(job_id, poll_interval, timeout, verbose)

        out_path.mkdir(parents=True, exist_ok=True)
        extracted = self._download_and_extract(job_id, out_path)
        if verbose:
            print(f'[pivotaljreport] {len(extracted)} pdf(s) -> {out_path}')

        return {
            'job_id':    job_id,
            'status':    status.get('status'),
            'requested': status.get('n_requested'),
            'completed': status.get('n_completed'),
            'out_dir':   str(out_path),
            'pdfs':      [str(p) for p in extracted],
            'error':     status.get('error'),
        }

    # ---- low-level ops ----
    def _upload(self, zip_bytes: bytes, folder_name: str,
                batch_tag: Optional[str]) -> dict:
        files = {'file': (f'{folder_name}.zip', zip_bytes, 'application/zip')}
        data = {'batch_tag': batch_tag} if batch_tag else {}
        r = requests.post(
            f'{self.base_url}/sdk/v1/reports',
            headers=self._auth_headers(),
            files=files, data=data, timeout=300,
        )
        return _raise_or_json(r)

    def status(self, job_id: str) -> dict:
        r = requests.get(
            f'{self.base_url}/sdk/v1/reports/{job_id}',
            headers=self._auth_headers(), timeout=30,
        )
        return _raise_or_json(r)

    def download(self, job_id: str) -> bytes:
        r = requests.get(
            f'{self.base_url}/sdk/v1/reports/{job_id}/download',
            headers=self._auth_headers(), timeout=300,
        )
        if r.status_code != 200:
            _raise_or_json(r)  # raises
        return r.content

    def _poll_until_done(self, job_id: str, poll_interval: float,
                         timeout: float, verbose: bool) -> dict:
        deadline = time.time() + timeout
        last_done = -1
        while True:
            s = self.status(job_id)
            st = s.get('status')
            done = s.get('n_completed') or 0
            total = s.get('n_requested') or 0
            if verbose and done != last_done:
                print(f'[pivotaljreport] {job_id} status={st} '
                      f'{done}/{total}')
                last_done = done
            if st in ('done', 'failed', 'partial'):
                if st == 'failed':
                    raise JobError(s.get('error') or 'job failed')
                return s
            if time.time() > deadline:
                raise JobError(
                    f'timed out waiting for job {job_id} '
                    f'(status={st}, {done}/{total})')
            time.sleep(poll_interval)

    def _download_and_extract(self, job_id: str, out: Path) -> list[Path]:
        blob = self.download(job_id)
        zf = zipfile.ZipFile(io.BytesIO(blob), 'r')
        written: list[Path] = []
        for name in zf.namelist():
            # Flatten: write every entry into out/ using its basename only,
            # to avoid zip-slip and preserve the 'one folder of PDFs' feel.
            safe = Path(name).name
            if not safe:
                continue
            target = out / safe
            with open(target, 'wb') as f:
                f.write(zf.read(name))
            written.append(target)
        return written


# --- module-level default client ---------------------------------------

_DEFAULT: Optional[Client] = None


def get_client() -> Client:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Client()
    return _DEFAULT


def authenticate(username: str, password: str,
                 base_url: Optional[str] = None) -> dict:
    """Log in the module-level default client."""
    global _DEFAULT
    _DEFAULT = Client(base_url=base_url) if base_url else Client()
    return _DEFAULT.authenticate(username=username, password=password)


def run(folder: Optional[str] = None, out: Optional[str] = None,
        **kwargs) -> dict:
    """Convenience: delegate to the default client's ``run()``.

    ``folder`` defaults to the current working directory.
    ``out``    defaults to ``<cwd>/<server-chosen-tag>`` (uniquified if
    that directory already exists).
    """
    return get_client().run(folder=folder, out=out, **kwargs)


# --- helpers -----------------------------------------------------------

def _zip_xlsx_folder(folder: Path) -> tuple[bytes, int]:
    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() != '.xlsx':
                continue
            zf.write(path, arcname=path.name)
            n += 1
    return buf.getvalue(), n


_PATH_UNSAFE = r'<>:"/\|?*'


def _sanitize_name(name: str) -> str:
    """Strip characters that Windows (or sensible humans) don't want in a
    directory name. Leaves the ``·`` separator alone since it's legal on
    every target filesystem and keeps the label readable."""
    cleaned = ''.join('_' if c in _PATH_UNSAFE else c for c in name)
    cleaned = cleaned.strip(' .')           # trailing dots/spaces are bad on Windows
    return cleaned or 'reports'


def _uniquify_dir(path: Path) -> Path:
    """Return ``path`` if it does not exist; otherwise append ``-1``, ``-2``,
    … until the name is free. Avoids clobbering a previous run's output."""
    if not path.exists():
        return path
    i = 1
    while True:
        candidate = path.with_name(f'{path.name}-{i}')
        if not candidate.exists():
            return candidate
        i += 1


def _raise_or_json(r: requests.Response) -> dict:
    try:
        body = r.json()
    except ValueError:
        body = {'error': r.text or f'HTTP {r.status_code}'}
    if r.status_code >= 400:
        err = body.get('error', f'HTTP {r.status_code}')
        if r.status_code == 401:
            raise AuthError(err)
        raise JobError(err)
    return body
