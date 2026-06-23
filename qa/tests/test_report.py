# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Unit tests for qa/report.py — JUnit error/failure split + CDATA safety.

Pure-logic coverage (no device): a scenario that died on an unexpected
exception must render as a JUnit <error> (and count in errors=), an assertion
failure as a <failure> (count in failures=), and any `]]>` in a message or log
line must not break XML well-formedness.
"""

import unittest
from xml.dom.minidom import parseString

import _paths  # noqa: F401

from qa.report import _render_junit
from qa.runner import ScenarioResult


def _result(name, *, passed, failure="", errored=False, logs=None):
    return ScenarioResult(
        name=name, passed=passed, duration_s=1.0,
        failure_message=failure, errored=errored,
        recent_logs=logs or [],
    )


class JunitErrorFailureSplit(unittest.TestCase):
    def test_counts_and_tags(self):
        results = [
            _result("ok", passed=True),
            _result("assert", passed=False, failure="expected X, got Y"),
            _result("boom", passed=False, failure="unexpected RuntimeError: kaboom",
                    errored=True),
        ]
        xml = _render_junit("suite", results)
        dom = parseString(xml)  # also asserts well-formedness
        ts = dom.getElementsByTagName("testsuite")[0]
        self.assertEqual(ts.getAttribute("tests"), "3")
        self.assertEqual(ts.getAttribute("failures"), "1")
        self.assertEqual(ts.getAttribute("errors"), "1")
        self.assertEqual(len(dom.getElementsByTagName("failure")), 1)
        self.assertEqual(len(dom.getElementsByTagName("error")), 1)

    def test_interrupted_attr(self):
        xml = _render_junit("suite", [_result("ok", passed=True)], interrupted=True)
        ts = parseString(xml).getElementsByTagName("testsuite")[0]
        self.assertEqual(ts.getAttribute("interrupted"), "true")


class CdataSafety(unittest.TestCase):
    def test_bracket_sequence_in_message_stays_well_formed(self):
        evil = 'failed at token ]]> in the stream'
        results = [_result("x", passed=False, failure=evil, logs=["log ]]> line"])]
        xml = _render_junit("suite", results)
        dom = parseString(xml)  # raises if the ]]> broke the CDATA section
        # The failure body must still carry the original text.
        failure = dom.getElementsByTagName("failure")[0]
        body = "".join(n.data for n in failure.childNodes)
        self.assertIn("]]>", body)


if __name__ == "__main__":
    unittest.main()
