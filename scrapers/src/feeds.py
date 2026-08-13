# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Data feeds: which payload variants `/api` serves, and under what names.

A **feed** is a served variant of the zone data, named by a positive integer.
Feed 1 is what has always shipped and keeps its URLs byte-for-byte; feed N>1
lives at `/api/zones.N`. Clients pick their feed at compile time and never
negotiate, so a feed is only ever fetched by apps built for it.

That is what the mechanism buys. `contracts/` pins the wire to what the 1.x
installs in the stores can parse, and it must keep pinning it for as long as
those installs exist — a client-side fix cannot reach a phone that already has
the app. A feed bump is the only way to serve a shape or a zone set those
clients could not consume, because they will never ask for it.

Everything version-dependent lives here:

- the filename rule (`feed == 1` means *no suffix* — the special case exists in
  exactly one place, this module);
- the projection registry, which turns the canonical `ZoneDatabase` into the
  view a given feed serves.

A projection returns a `ZoneDatabase`, which is then hashed and serialized
through the ordinary path. So a feed may drop zones, alter values, or omit
fields (leave them `None` — `exclude_none=True` keeps them off the wire), and
feed 1's projection being the identity is what guarantees its output does not
move by a single byte. A feed needing a shape `ZoneDatabase` cannot express is
the point at which to widen this contract — deliberately, with the model change
reviewed against `contracts/`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from src.client_contract import (
    DEFAULT_FEED,
    SERVED_FEED_STATUSES,
    ContractError,
    load_feeds,
)
from src.zone_schema import ZoneDatabase

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_FEED",
    "FEED_CONFIG_ERRORS",
    "FeedError",
    "is_unsupported",
    "project",
    "served_feeds",
    "snapshot_glob",
    "snapshot_name",
    "version_filename",
    "zones_filename",
]

Projection = Callable[[ZoneDatabase], ZoneDatabase]


class FeedError(RuntimeError):
    """A feed is declared but cannot be published (e.g. no projection)."""


def _suffix(feed: int) -> str:
    """``''`` for feed 1, ``'.N'`` beyond.

    Feed 1 carrying no suffix is the compatibility promise: every install ever
    published fetches `/api/zones`, and that URL must keep resolving to the
    same file forever.
    """
    return "" if feed == DEFAULT_FEED else f".{feed}"


def zones_filename(feed: int) -> str:
    return f"zones{_suffix(feed)}.json"


def version_filename(feed: int) -> str:
    return f"version{_suffix(feed)}.json"


def snapshot_name(feed: int, timestamp: str) -> str:
    return f"zones{_suffix(feed)}-{timestamp}.json"


def snapshot_glob(feed: int) -> str:
    """Glob matching only *this* feed's snapshots.

    Note `zones-*.json` would also match `zones.2-<ts>.json` — the feed-1 glob
    has to exclude the dot, or rotating feed 1 would prune feed 2's history.
    """
    return f"zones{_suffix(feed)}-[0-9]*.json"


def _project_identity(db: ZoneDatabase) -> ZoneDatabase:
    return db


# Feed -> projection. Feed 1 is the identity: its bytes must not move.
PROJECTIONS: dict[int, Projection] = {
    1: _project_identity,
}


def project(db: ZoneDatabase, feed: int) -> ZoneDatabase:
    """The view of ``db`` that ``feed`` serves, hashed for that view.

    The hash covers the *projected* zones, so a feed whose content differs
    carries a different hash and its clients actually resync. Feed 1's
    projection is the identity, so its hash is computed from exactly the input
    it always was — anything else would re-hash the shipping catalog and force
    a pointless full resync of the entire fleet.
    """
    projection = PROJECTIONS.get(feed)
    if projection is None:
        # Never fall back to feed 1: silently serving the old shape under a new
        # feed's name is worse than not serving it.
        raise FeedError(
            f"feed {feed} is declared in contracts/manifest.json but has no "
            f"projection in src/feeds.py — add one, or retire the feed"
        )
    return projection(db).with_hash()


def served_feeds(contracts_dir: Path | None = None) -> list[dict]:
    """Feeds that must be written this run, ascending.

    `retired` feeds are skipped (their files are left alone rather than
    deleted — a rollback should not need a re-scrape). Every served feed is
    checked for a projection up front, so a misconfiguration fails before any
    file is written rather than half-way through the loop.
    """
    feeds = [f for f in load_feeds(contracts_dir) if f["status"] in SERVED_FEED_STATUSES]
    if not feeds:
        raise FeedError("no served feeds — every declared feed is retired")
    missing = [f["version"] for f in feeds if f["version"] not in PROJECTIONS]
    if missing:
        raise FeedError(
            f"served feed(s) {missing} have no projection in src/feeds.py"
        )
    return feeds


def is_unsupported(feed_entry: dict) -> bool:
    """Whether this feed's `version.json` gets the `"unsupported"` flag."""
    return feed_entry["status"] == "unsupported"


# Re-exported so callers can catch one exception type for "the feed
# configuration is unusable", however it failed.
FEED_CONFIG_ERRORS = (FeedError, ContractError)
