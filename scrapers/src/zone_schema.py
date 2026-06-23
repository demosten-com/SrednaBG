# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Pydantic models for the SrednaBG zone data schema.

These models define the structure of zones.json — the unified zone database
consumed by the Android app, backend, and core calculation engine.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Bulgaria bounding box (approximate)
BG_LAT_MIN = 41.2
BG_LAT_MAX = 44.2
BG_LNG_MIN = 22.3
BG_LNG_MAX = 28.7


class ZoneEndpoint(BaseModel):
    """A start or end point of a speed control zone."""

    model_config = ConfigDict(populate_by_name=True)

    lat: float
    lng: float
    km_marker: str | None = None
    settlement: str | None = None
    settlement_latin: str | None = None


class SpeedLimits(BaseModel):
    """Speed limits by vehicle type in km/h."""

    car: int
    truck: int
    bus: int
    motorcycle: int | None = None


class Zone(BaseModel):
    """A single average speed enforcement zone."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    road: str
    road_latin: str | None = None
    direction: str
    description: str
    start: ZoneEndpoint
    end: ZoneEndpoint
    distance_m: int
    speed_limits: SpeedLimits
    centerline: list[list[float]]
    road_type: str | None = None  # "motorway" or "road"
    source: str
    last_verified: str

    @field_validator("distance_m")
    @classmethod
    def distance_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("distance_m must be positive")
        return v

    @field_validator("direction")
    @classmethod
    def direction_must_be_valid(cls, v: str) -> str:
        valid = {"east", "west", "north", "south"}
        if v not in valid:
            raise ValueError(f"direction must be one of {valid}, got '{v}'")
        return v

    @model_validator(mode="after")
    def check_coordinates_in_bulgaria(self) -> "Zone":
        """Reject coordinates outside Bulgaria (allow 0,0 for unknown).

        Raises ``ValueError`` so a scraper that produced out-of-bbox coords
        (e.g. a bug placing a zone in Serbia/Greece) drops *that zone* via the
        per-zone ``try/except`` in each scraper, rather than shipping it.
        """
        for endpoint in [self.start, self.end]:
            if endpoint.lat == 0.0 and endpoint.lng == 0.0:
                continue  # Placeholder for unknown coordinates
            if not (BG_LAT_MIN <= endpoint.lat <= BG_LAT_MAX):
                raise ValueError(
                    f"Latitude {endpoint.lat} outside Bulgaria "
                    f"({BG_LAT_MIN}-{BG_LAT_MAX})"
                )
            if not (BG_LNG_MIN <= endpoint.lng <= BG_LNG_MAX):
                raise ValueError(
                    f"Longitude {endpoint.lng} outside Bulgaria "
                    f"({BG_LNG_MIN}-{BG_LNG_MAX})"
                )
        return self


class ZoneDatabase(BaseModel):
    """The complete zone database with version and integrity hash."""

    version: str
    hash: str = ""
    zones: list[Zone]

    # Fields whose value changes with the run timestamp but not with zone data.
    # Excluded from the integrity hash so that re-running the pipeline on a
    # different day with otherwise-identical scraped data yields the same hash.
    HASH_EXCLUDE: ClassVar[set[str]] = {"last_verified"}

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of the zones data.

        Excludes per-zone re-verification timestamps so the hash reflects
        actual data changes only.
        """
        zones_json = json.dumps(
            [z.model_dump(exclude=self.HASH_EXCLUDE) for z in self.zones],
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        digest = hashlib.sha256(zones_json).hexdigest()
        return f"sha256:{digest}"

    def with_hash(self) -> "ZoneDatabase":
        """Return a copy with the hash field computed."""
        return self.model_copy(update={"hash": self.compute_hash()})

    @staticmethod
    def now_version() -> str:
        """Generate a version string from the current UTC time."""
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
