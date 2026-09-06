"""Deprecated alias of components.section.section.

Kept only so pages not yet migrated to the 2026-09-06 restyle keep rendering. It
delegates rather than duplicating, so a half-migrated app cannot show two different
section treatments side by side. Removed once no page imports it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from components.section import section


@contextmanager
def card(title: str) -> Iterator[None]:
    with section(title):
        yield
