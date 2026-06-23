# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Parity test for qa/speech_numbers.py — the hand-port of the app's number
speller (`SpeechNumbers.kt` / `SpeechNumbers.swift`).

`vehicle_type_limit_badge` asserts the *spelled* speed limit appears in the
app's TTS output via this Python port. If the port drifts from the app, that
assertion silently breaks (or false-passes). Two guards, both headless:

1. The word-list arrays are extracted from the Kotlin source (the oracle) and
   compared element-for-element against the Python module's arrays — catches a
   typo / changed word.
2. A hand-verified expected table pins the assembly rules (EN hyphen, BG "и"
   conjunction, hundreds) for representative speeds.
"""

import re
import unittest

from _paths import REPO_ROOT  # bootstraps sys.path for `from qa import …`

from qa import speech_numbers as sn

KT_SRC = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com"
          / "demosten" / "srednabg" / "app" / "ui" / "util" / "SpeechNumbers.kt")


def _kotlin_list(text: str, name: str) -> list[str]:
    m = re.search(rf"val {name} = listOf\((.*?)\)", text, re.S)
    if not m:
        raise AssertionError(f"could not find Kotlin list {name} in {KT_SRC}")
    return re.findall(r'"([^"]*)"', m.group(1))


class KotlinArrayParityTests(unittest.TestCase):
    """The Python word arrays must match the Kotlin source verbatim."""

    @classmethod
    def setUpClass(cls):
        cls.text = KT_SRC.read_text(encoding="utf-8")

    def _assert_match(self, kt_name, py_array):
        self.assertEqual(_kotlin_list(self.text, kt_name), py_array,
                         f"{kt_name} drifted between SpeechNumbers.kt and qa/speech_numbers.py")

    def test_en_ones(self):
        self._assert_match("EN_ONES", sn._EN_ONES)

    def test_en_teens(self):
        self._assert_match("EN_TEENS", sn._EN_TEENS)

    def test_en_tens(self):
        self._assert_match("EN_TENS", sn._EN_TENS)

    def test_bg_ones(self):
        self._assert_match("BG_ONES", sn._BG_ONES)

    def test_bg_teens(self):
        self._assert_match("BG_TEENS", sn._BG_TEENS)

    def test_bg_tens(self):
        self._assert_match("BG_TENS", sn._BG_TENS)

    def test_bg_hundreds(self):
        self._assert_match("BG_HUNDREDS", sn._BG_HUNDREDS)


# Hand-verified against SpeechNumbers.kt's assembly rules. These are the oracle
# for the spelled forms the app produces (and thus what the QA assertion sees).
EXPECTED_EN = {
    0: "zero", 5: "five", 10: "ten", 19: "nineteen", 20: "twenty",
    25: "twenty-five", 90: "ninety", 100: "one hundred", 105: "one hundred five",
    120: "one hundred twenty", 125: "one hundred twenty-five",
    140: "one hundred forty", 200: "two hundred", 999: "nine hundred ninety-nine",
}
EXPECTED_BG = {
    0: "нула", 5: "пет", 10: "десет", 19: "деветнадесет", 20: "двадесет",
    25: "двадесет и пет", 90: "деветдесет", 100: "сто", 105: "сто и пет",
    120: "сто и двадесет", 125: "сто двадесет и пет",
    140: "сто и четиридесет", 200: "двеста",
    999: "деветстотин деветдесет и девет",
}


class ExpectedSpellingTests(unittest.TestCase):
    def test_english(self):
        for n, expected in EXPECTED_EN.items():
            self.assertEqual(sn.words(n, bulgarian=False), expected, f"EN {n}")

    def test_bulgarian(self):
        for n, expected in EXPECTED_BG.items():
            self.assertEqual(sn.words(n, bulgarian=True), expected, f"BG {n}")

    def test_out_of_range_is_digit_string(self):
        self.assertEqual(sn.words(1000, bulgarian=False), "1000")
        self.assertEqual(sn.words(-3, bulgarian=True), "-3")


if __name__ == "__main__":
    unittest.main()
