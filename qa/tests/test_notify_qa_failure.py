# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""QA notifications survive broken reports; all sending is mocked."""

import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import _paths  # noqa: F401

from qa.report import _render_junit
from qa.runner import ScenarioResult


SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/notify-qa-failure.py"
spec = importlib.util.spec_from_file_location("notify_qa_failure", SCRIPT)
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


class NotificationReports(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(tmp)
        self.enterContext(patch.object(notify, "REPO_ROOT", self.root))
        self.enterContext(patch.object(notify, "REPORTS", self.root / "reports"))
        self.run_url = "https://github.com/demosten-com/SrednaBG/actions/runs/123"
        self.enterContext(patch.dict(os.environ, {
            "PLATFORMS": "both", "SUITE": "nightly", "RUN_URL": self.run_url,
        }, clear=True))
        self.enterContext(patch("sys.stderr", new_callable=io.StringIO))

    def write_report(self, platform, text):
        path = self.root / "reports" / platform / "nightly-test" / "junit.xml"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_generated_quoted_failure_reaches_notification(self):
        result = ScenarioResult(name='zone "A"', passed=False, duration_s=0,
                                failure_message='Traceback: File "/tmp/qa.py", line 144')
        path = self.write_report("android", _render_junit("nightly", [result]))
        self.assertEqual(notify._failed_cases(path), (1, [(result.name, result.failure_message)]))
        message = notify.build_message()
        self.assertIn("<b>android</b>: 1 of 1 failed", message)
        self.assertIn("&quot;/tmp/qa.py&quot;", message)
        self.assertIn(self.run_url, message)

    def test_malformed_report_still_sends_other_platform_and_run_link(self):
        self.write_report("android", '<testsuite><failure message="File "/tmp/qa.py""/>')
        self.write_report("ios", _render_junit("nightly", [
            ScenarioResult(name="ok", passed=True, duration_s=1),
        ]))
        with patch.object(notify, "send_telegram", return_value=True) as send:
            self.assertEqual(notify.main([]), 0)
        send.assert_called_once()
        message = send.call_args.args[0]
        self.assertIn("<b>android</b>: report unavailable or invalid", message)
        self.assertIn("<b>ios</b>: 1/1 passed", message)
        self.assertIn(self.run_url, message)

    def test_unreadable_report_still_includes_run_link(self):
        self.write_report("android", "<testsuite/>")
        with patch.object(notify, "_failed_cases", side_effect=PermissionError):
            message = notify.build_message()
        self.assertIn("<b>android</b>: report unavailable or invalid", message)
        self.assertIn("<b>ios</b>: no report", message)
        self.assertIn(self.run_url, message)

    def test_report_discovery_failure_still_includes_run_link(self):
        with patch.object(notify, "_latest_junit", side_effect=FileNotFoundError):
            message = notify.build_message()
        for platform in ("android", "ios"):
            self.assertIn(f"<b>{platform}</b>: report unavailable or invalid", message)
        self.assertIn(self.run_url, message)


if __name__ == "__main__":
    unittest.main()
