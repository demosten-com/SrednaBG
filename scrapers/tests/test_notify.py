# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Tests for the Telegram cron-notification formatting and helpers."""

from src import notify


class TestShortHash:
    def test_none_and_dash(self):
        assert notify._short_hash("") == "(none)"
        assert notify._short_hash("-") == "(none)"

    def test_sha256_trimmed_to_14_hex(self):
        h = "sha256:" + "a" * 64
        out = notify._short_hash(h)
        assert out == "sha256:" + "a" * 14 + "…"

    def test_non_sha_prefix_truncated(self):
        assert notify._short_hash("x" * 40) == "x" * 20


class TestFormatSuccess:
    def test_changed_no_when_hashes_equal(self):
        h = "sha256:" + "b" * 64
        msg = notify.format_success(72, h, h, 12)
        assert "zones: <b>72</b>" in msg
        assert "changed: <b>no</b>" in msg
        assert "duration: 12s" in msg

    def test_changed_yes_when_hashes_differ(self):
        msg = notify.format_success(
            72, "sha256:" + "a" * 64, "sha256:" + "b" * 64, 5
        )
        assert "changed: <b>yes</b>" in msg

    def test_changed_yes_when_prev_missing(self):
        msg = notify.format_success(72, "sha256:" + "a" * 64, "", 5)
        assert "changed: <b>yes</b>" in msg


class TestFormatFailure:
    def test_includes_rc_and_escaped_tail(self):
        msg = notify.format_failure(3, 9, "boom <script> & co")
        assert "rc=3" in msg
        assert "duration: 9s" in msg
        # HTML-escaped so the <pre> block stays well-formed.
        assert "&lt;script&gt;" in msg
        assert "&amp;" in msg

    def test_empty_tail_placeholder(self):
        msg = notify.format_failure(1, 0, "")
        assert "(no log content)" in msg


class TestTail:
    def test_returns_last_n_lines(self, tmp_path):
        p = tmp_path / "cron.log"
        p.write_text("".join(f"line{i}\n" for i in range(10)))
        assert notify._tail(p, 3) == "line7\nline8\nline9\n"

    def test_unreadable_returns_empty(self, tmp_path):
        assert notify._tail(tmp_path / "missing.log", 5) == ""


class TestCountFromState:
    def test_parses_latest_result_line(self, tmp_path):
        p = tmp_path / "cron.log"
        p.write_text(
            "RESULT zone_count=10 hash=x\n"
            "some other line\n"
            "RESULT zone_count=72 hash=y\n"
        )
        assert notify._count_from_state(p) == 72

    def test_no_result_line_returns_zero(self, tmp_path):
        p = tmp_path / "cron.log"
        p.write_text("nothing useful here\n")
        assert notify._count_from_state(p) == 0

    def test_unreadable_returns_zero(self, tmp_path):
        assert notify._count_from_state(tmp_path / "missing.log") == 0


class TestSendTelegram:
    def test_no_op_without_env(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        # Must not attempt any network call when creds are absent.
        called = False

        def _fail(*a, **k):
            nonlocal called
            called = True
            raise AssertionError("network should not be reached")

        monkeypatch.setattr(notify.requests, "post", _fail)
        assert notify.send_telegram("hi") is False
        assert called is False
