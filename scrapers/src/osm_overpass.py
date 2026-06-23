# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Query OSM Overpass API for average speed enforcement data in Bulgaria.

As of 2026-06, OSM has zero enforcement=average_speed relations in Bulgaria.
This module exists for future-proofing — if the OSM community adds this data,
the scraper will automatically pick it up.
"""

import logging

import overpy

from src.zone_schema import Zone

logger = logging.getLogger(__name__)

# Bulgaria bounding box (south, west, north, east)
BG_BBOX = (41.2, 22.3, 44.2, 28.7)


def query_average_speed_relations(api: overpy.Overpass | None = None) -> list:
    """Query Overpass for enforcement=average_speed relations in Bulgaria."""
    if api is None:
        api = overpy.Overpass()

    query = f"""
    [out:json][timeout:60];
    (
      relation["enforcement"="average_speed"]({BG_BBOX[0]},{BG_BBOX[1]},{BG_BBOX[2]},{BG_BBOX[3]});
    );
    out body;
    >;
    out skel qt;
    """

    try:
        result = api.query(query)
        relations = list(result.relations)
        logger.info("Overpass returned %d average_speed relations", len(relations))
        return relations
    except overpy.exception.OverpassTooManyRequests:
        logger.warning("Overpass API rate limited, skipping")
        return []
    except overpy.exception.OverpassGatewayTimeout:
        logger.warning("Overpass API timeout, skipping")
        return []
    except overpy.exception.OverpassUnknownHTTPStatusCode as e:
        # Overpass intermittently answers with non-standard codes (e.g. 406)
        # when the public endpoint is overloaded. There's no BG average_speed
        # data to lose, so log a one-liner instead of a full traceback.
        logger.warning("Overpass returned an unexpected HTTP status, skipping: %s", e)
        return []
    except Exception:
        logger.warning("Overpass query failed", exc_info=True)
        return []


def scrape() -> list[Zone]:
    """Main entry point. Query Overpass and convert to zones.

    Currently returns empty list since no enforcement=average_speed
    data exists in OSM for Bulgaria.
    """
    try:
        relations = query_average_speed_relations()
        if not relations:
            logger.info(
                "No OSM enforcement=average_speed data for Bulgaria. "
                "This is expected as of 2026-06."
            )
            return []

        # Future: convert relations to Zone objects
        logger.info(
            "Found %d OSM relations — conversion not yet implemented",
            len(relations),
        )
        return []
    except Exception:
        logger.warning("OSM Overpass scraper failed", exc_info=True)
        return []
