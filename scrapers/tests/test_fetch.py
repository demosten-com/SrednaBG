# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the shared retrying HTTP fetcher."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.fetch import ATTEMPTS, fetch_text


def _resp(status: int = 200, text: str = "ok") -> MagicMock:
    """Build a fake requests.Response whose raise_for_status mirrors the status."""
    r = MagicMock()
    r.status_code = status
    r.text = text
    if status >= 400:
        err = requests.HTTPError(f"{status} error")
        err.response = r
        r.raise_for_status.side_effect = err
    else:
        r.raise_for_status.return_value = None
    return r


@patch("src.fetch.time.sleep", lambda *_: None)  # no real backoff delay
class TestGetRetry:
    def test_retries_transient_then_succeeds(self):
        # Two connection errors, then a 200.
        side = [requests.ConnectionError("boom"), requests.ConnectionError("boom"), _resp(200)]
        with patch("src.fetch.requests.get", side_effect=side) as mock_get:
            assert fetch_text("http://x") == "ok"
            assert mock_get.call_count == ATTEMPTS

    def test_4xx_fails_fast_without_retry(self):
        with patch("src.fetch.requests.get", return_value=_resp(404)) as mock_get:
            with pytest.raises(requests.HTTPError):
                fetch_text("http://x")
            assert mock_get.call_count == 1  # no retries on a client error

    def test_5xx_retries_until_exhausted(self):
        with patch("src.fetch.requests.get", return_value=_resp(503)) as mock_get:
            with pytest.raises(requests.HTTPError):
                fetch_text("http://x")
            assert mock_get.call_count == ATTEMPTS
