# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Shared HTTP fetching with retry + backoff for the upstream sources."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

USER_AGENT = "SrednaBG/1.0 (zone-scraper)"
ATTEMPTS = 3
BACKOFF_BASE_S = 2.0  # 2s, then 4s between the three attempts


def _get(url: str, timeout: int, label: str) -> requests.Response:
    last_exc: requests.RequestException | None = None
    for attempt in range(ATTEMPTS):
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            logger.warning("%s fetch attempt %d failed: %s", label, attempt + 1, e)
            if attempt < ATTEMPTS - 1:
                time.sleep(BACKOFF_BASE_S * 2**attempt)
    raise last_exc  # type: ignore[misc]


def fetch_text(url: str, *, timeout: int = 30, label: str = "HTTP") -> str:
    """GET ``url`` and return its body as UTF-8 text, retrying with backoff."""
    resp = _get(url, timeout, label)
    resp.encoding = "utf-8"
    return resp.text


def fetch_bytes(url: str, *, timeout: int = 30, label: str = "HTTP") -> bytes:
    """GET ``url`` and return its raw body, retrying with backoff."""
    return _get(url, timeout, label).content
