# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin.slugs | slug generation helpers for admin routes."""

import re


def slugify(name: str) -> str:
    """strip non-alphanumeric/space/dash chars, lowercase, spaces to dashes, collapse dashes."""
    name = re.sub(r'[^a-zA-Z0-9 -]', '', name)
    name = name.lower()
    name = name.replace(' ', '-')
    name = re.sub(r'-+', '-', name)
    return name


def make_slug_map(items: list[dict]) -> dict[str, dict]:
    """build {slug: item} map; collision resolution: base, -2, -3, ..."""
    result: dict[str, dict] = {}
    slug_counts: dict[str, int] = {}
    for item in items:
        base = slugify(item['name'])
        count = slug_counts.get(base, 0)
        slug_counts[base] = count + 1
        slug = base if count == 0 else f'{base}-{count + 1}'
        result[slug] = item
    return result
