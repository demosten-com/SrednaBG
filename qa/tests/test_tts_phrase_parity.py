# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""TTS phrase parity: Android `AudioAlertManager.kt` ⇄ iOS `TtsPhrases.swift`.

Replaces the old `_extract_tts.py` fixture (which read only the Android source,
so iOS phrase drift was invisible and nothing consumed the output anyway). Here
we parse the spoken-phrase string literals from BOTH platforms, normalise the
spelled-number interpolation to a common placeholder, and assert the two phrase
sets are identical — so a phrase that changes on one platform but not the other
fails loudly in CI.
"""

import re
import unittest

from _paths import REPO_ROOT  # bootstraps sys.path for `from qa import …`

KT_SRC = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin" / "com"
          / "demosten" / "srednabg" / "app" / "service" / "AudioAlertManager.kt")
SWIFT_SRC = (REPO_ROOT / "ios" / "Packages" / "SrednaBGTracking" / "Sources"
             / "SrednaBGTracking" / "TtsPhrases.swift")

# A spoken-phrase literal carries one of these marker words (skips TAG, locale
# codes, log strings, etc.).
MARKERS = (
    "Влизате", "Entering", "Средна", "Средната", "Average", "Внимание",
    "Warning", "отново в норма", "Back within", "Излизате", "Leaving",
)

PLACEHOLDER = "{N}"
# Kotlin: "… ${SpeechNumbers.toWords(limit, bulgarian = true)}."
KT_INTERP = re.compile(r"\$\{SpeechNumbers\.toWords\([^)]*\)\}")
# Swift:  "… \(SpeechNumbers.words(limit, bulgarian: bg))."
SWIFT_INTERP = re.compile(r"\\\(SpeechNumbers\.words\([^)]*\)\)")


def _phrases(text: str, interp: re.Pattern) -> set[str]:
    out = set()
    for lit in re.findall(r'"([^"]*)"', text):
        if any(m in lit for m in MARKERS):
            out.add(interp.sub(PLACEHOLDER, lit).strip())
    return out


class TtsPhraseParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kt = _phrases(KT_SRC.read_text(encoding="utf-8"), KT_INTERP)
        cls.sw = _phrases(SWIFT_SRC.read_text(encoding="utf-8"), SWIFT_INTERP)

    def test_found_phrases(self):
        # 5 events × 2 languages = 10 distinct phrases per platform.
        self.assertEqual(len(self.kt), 10, f"Kotlin phrases: {sorted(self.kt)}")
        self.assertEqual(len(self.sw), 10, f"Swift phrases: {sorted(self.sw)}")

    def test_no_unresolved_interpolation(self):
        # Every spelled-number slot was normalised (no stray ${…} / \(…)).
        for p in self.kt | self.sw:
            self.assertNotIn("SpeechNumbers", p, f"unresolved interpolation in {p!r}")

    def test_phrase_sets_match(self):
        only_kt = self.kt - self.sw
        only_sw = self.sw - self.kt
        self.assertFalse(
            only_kt or only_sw,
            "TTS phrases drifted between platforms.\n"
            f"  Android-only: {sorted(only_kt)}\n"
            f"  iOS-only:     {sorted(only_sw)}")


if __name__ == "__main__":
    unittest.main()
