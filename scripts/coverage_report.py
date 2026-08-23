#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""scripts.coverage_report | coverage report generator for pytest-cov output."""

import argparse
import json
import pathlib
import sys
from collections import defaultdict
from datetime import date


# --- formatting ---

SUMMARY_HEADER = '| Statements | Miss | Branch | Branch Parts | Coverage |\n|------:|-----:|-------:|-------:|------:|'

MODULE_HEADER = '| Module | Statements | Miss | Branch | Branch Parts | Coverage |\n|--------|------:|-----:|-------:|-------:|------:|'


def summary_row(s: dict) -> str:
    """format a totals/summary block as a single right-aligned table row."""
    return f'| {s["num_statements"]} | {s["missing_lines"]} | {s["num_branches"]} | {s["num_partial_branches"]} | {s["percent_covered_display"]}% |'


def module_row(path: str, s: dict) -> str:
    """format a single file's summary as a table row prefixed with its path."""
    return f'| {path} | {s["num_statements"]} | {s["missing_lines"]} | {s["num_branches"]} | {s["num_partial_branches"]} | {s["percent_covered_display"]}% |'


# --- grouping ---


def package_sort_key(pkg: str) -> tuple[int, str]:
    """sort the bare top-level package first, then alphabetical by path."""
    # one slash means top-level (e.g. "nova_core"); deeper paths sort after
    return (pkg.count('/'), pkg)


def group_by_package(files: dict, strip_prefix: str) -> dict[str, list[tuple[str, dict]]]:
    """strip the prefix off each path and bucket files by their parent dir."""
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for raw_path, entry in files.items():
        path = raw_path
        if strip_prefix and path.startswith(strip_prefix):
            path = path[len(strip_prefix) :]
        pkg = str(pathlib.Path(path).parent) if '/' in path else path
        groups[pkg].append((path, entry['summary']))
    for pkg, entries in groups.items():
        entries.sort(key=lambda item: item[0])
    return groups


# --- emission ---


def emit_report(data: dict, strip_prefix: str, top_misses: int) -> str:
    """build the markdown report string from a parsed coverage.json document."""
    lines: list[str] = ['## coverage', '']
    lines.append(SUMMARY_HEADER)
    lines.append(summary_row(data['totals']))
    lines.append('')

    groups = group_by_package(data['files'], strip_prefix)
    for pkg in sorted(groups, key=package_sort_key):
        lines.append(f'### {pkg}')
        lines.append('')
        lines.append(MODULE_HEADER)
        for path, summary in groups[pkg]:
            lines.append(module_row(path, summary))
        lines.append('')

    if top_misses > 0:
        all_files = []
        for raw_path, entry in data['files'].items():
            path = raw_path
            if strip_prefix and path.startswith(strip_prefix):
                path = path[len(strip_prefix) :]
            all_files.append((path, entry['summary']))
        # ascending coverage; ties broken by larger missing_lines first
        all_files.sort(key=lambda item: (item[1]['percent_covered'], -item[1]['missing_lines']))
        lines.append(f'### lowest coverage (top {top_misses})')
        lines.append('')
        lines.append(MODULE_HEADER)
        for path, summary in all_files[:top_misses]:
            lines.append(module_row(path, summary))
        lines.append('')

    today = date.today()
    lines.append('## metadata')
    lines.append('')
    lines.append('```yaml')
    lines.append(f'last_updated: {today.day} {today.strftime("%B %Y")}')
    lines.append('```')

    return '\n'.join(lines).rstrip() + '\n'


# --- io ---


def load_report(path: str) -> dict:
    """read coverage json from a file path or '-' for stdin."""
    if path == '-':
        return json.load(sys.stdin)
    with pathlib.Path(path).open(encoding='utf-8') as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='render a pytest-cov json report as the markdown coverage section used in notes/to-do.md',
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='-',
        help='path to coverage.json (or "-" for stdin; default: stdin)',
    )
    parser.add_argument(
        '--strip-prefix',
        default='apps/bot/',
        help='prefix to strip from file paths in the report (default: apps/bot/)',
    )
    parser.add_argument(
        '--top-misses',
        type=int,
        default=0,
        metavar='N',
        help='append a "lowest coverage" section listing the N worst modules',
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=None,
        metavar='PCT',
        help='exit 1 if total percent_covered is below PCT',
    )
    parser.add_argument(
        '-o',
        '--output',
        default='-',
        metavar='PATH',
        help='write the report to PATH instead of stdout (use "-" for stdout; default: stdout)',
    )
    args = parser.parse_args()

    try:
        data = load_report(args.path)
    except FileNotFoundError:
        print(f'error: file not found: {args.path}', file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f'error: invalid json in {args.path}: {e}', file=sys.stderr)
        return 1

    if 'files' not in data or 'totals' not in data:
        print('error: input does not look like a coverage.py json report (missing "files" or "totals")', file=sys.stderr)
        return 1

    report = emit_report(data, args.strip_prefix, args.top_misses)
    if args.output == '-':
        sys.stdout.write(report)
    else:
        try:
            with pathlib.Path(args.output).open('w', encoding='utf-8') as f:
                f.write(report)
        except OSError as e:
            print(f'error: could not write to {args.output}: {e}', file=sys.stderr)
            return 1

    if args.threshold is not None and data['totals']['percent_covered'] < args.threshold:
        print(
            f'coverage {data["totals"]["percent_covered"]:.2f}% below threshold {args.threshold}%',
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
