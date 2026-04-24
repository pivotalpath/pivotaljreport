"""pivotaljreport — thin Python client for the jreport SDK API.

Canonical usage::

    import pivotaljreport as pr

    pr.authenticate(username="alice", password="...")
    pr.run(folder="./data", out="./reports")

``run()`` zips the folder's ``.xlsx`` files, uploads to the server,
polls until the job finishes, then extracts the returned PDFs into
``out``. It is synchronous on the surface — pass ``timeout=`` if you
need to bail on slow jobs.

Auth is a placeholder (username/password). Do not commit real
credentials; read them from an env var or prompt the user.
"""
from __future__ import annotations

from .client import (
    authenticate,
    run,
    get_client,
    Client,
    AuthError,
    JobError,
)

__all__ = [
    'authenticate', 'run', 'get_client', 'Client',
    'AuthError', 'JobError',
]

__version__ = '0.1.1'
