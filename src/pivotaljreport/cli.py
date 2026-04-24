"""Command-line entry point.

Registered as the ``pivotaljreport`` console script via
``[project.scripts]`` in pyproject.toml. Thin wrapper over the
``Client`` API — no behaviour lives here that isn't already in
``client.py``.

Usage::

    pivotaljreport run ./data --out ./reports --username alice
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Optional

from . import __version__
from .client import (
    Client,
    DEFAULT_BASE_URL,
    AuthError,
    JobError,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='pivotaljreport',
        description='PivotalPath jreport client.',
    )
    p.add_argument('--version', action='version',
                   version=f'pivotaljreport {__version__}')

    sub = p.add_subparsers(dest='command', required=True)

    run = sub.add_parser(
        'run',
        help='Generate reports for every .xlsx in a folder.',
    )
    run.add_argument('folder',
                     help='Local folder containing .xlsx input files.')
    run.add_argument('--out', default='./reports',
                     help='Where to write generated PDFs (default: ./reports).')
    run.add_argument('--username',
                     default=os.getenv('PIVOTALJREPORT_USERNAME'),
                     help='Account username (env: PIVOTALJREPORT_USERNAME).')
    run.add_argument('--password',
                     default=os.getenv('PIVOTALJREPORT_PASSWORD'),
                     help='Account password (env: PIVOTALJREPORT_PASSWORD). '
                          'If omitted, prompts interactively.')
    run.add_argument('--base-url',
                     default=os.getenv('PIVOTALJREPORT_BASE_URL',
                                       DEFAULT_BASE_URL),
                     help=f'Server base URL (default: {DEFAULT_BASE_URL}, '
                          'env: PIVOTALJREPORT_BASE_URL).')
    run.add_argument('--tag', default=None,
                     help='Human-readable label for the batch.')
    run.add_argument('--timeout', type=float, default=1800.0,
                     help='Max seconds to wait for the job (default: 1800).')
    run.add_argument('--poll-interval', type=float, default=3.0,
                     help='Status-poll interval in seconds (default: 3).')
    run.add_argument('--quiet', action='store_true',
                     help='Suppress progress prints.')
    run.add_argument('--json', action='store_true',
                     help='Print the final result as JSON on stdout.')
    return p


def _resolve_password(username: str, password: Optional[str]) -> str:
    if password:
        return password
    if not sys.stdin.isatty():
        raise SystemExit(
            'error: --password (or PIVOTALJREPORT_PASSWORD) required when '
            'stdin is not a terminal'
        )
    return getpass.getpass(f'Password for {username}: ')


def _cmd_run(args: argparse.Namespace) -> int:
    if not args.username:
        print('error: --username (or PIVOTALJREPORT_USERNAME) is required',
              file=sys.stderr)
        return 2

    password = _resolve_password(args.username, args.password)

    client = Client(base_url=args.base_url)
    try:
        client.authenticate(username=args.username, password=password)
    except AuthError as exc:
        print(f'authentication failed: {exc}', file=sys.stderr)
        return 1

    try:
        result = client.run(
            folder=args.folder,
            out=args.out,
            batch_tag=args.tag,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
            verbose=not args.quiet,
        )
    except (AuthError, JobError, FileNotFoundError, ValueError) as exc:
        print(f'run failed: {exc}', file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    elif not args.quiet:
        print(f'ok — {len(result.get("pdfs", []))} pdf(s) in '
              f'{result.get("out_dir")}')
    return 0


def main(argv: Optional[list] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == 'run':
        return _cmd_run(args)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
