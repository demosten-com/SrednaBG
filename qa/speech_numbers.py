# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Spell an integer speed into words, mirroring the in-app helpers
(`android/.../ui/util/SpeechNumbers.kt` and `ios/.../SpeechNumbers.swift`).

The apps spell speeds into words before handing them to TTS so the engine never
reads a number digit-by-digit. QA assertions that look for a spoken speed must
therefore match the spelled form, not the bare digits — use `words()` here so a
scenario stays meaningful (e.g. a truck limit of 90 is still distinguishable
from a car limit of 140) and identical across both platforms.
"""

_EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_EN_TEENS = ["ten", "eleven", "twelve", "thirteen", "fourteen",
             "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

_BG_ONES = ["нула", "едно", "две", "три", "четири", "пет", "шест", "седем", "осем", "девет"]
_BG_TEENS = ["десет", "единадесет", "дванадесет", "тринадесет", "четиринадесет",
             "петнадесет", "шестнадесет", "седемнадесет", "осемнадесет", "деветнадесет"]
_BG_TENS = ["", "", "двадесет", "тридесет", "четиридесет",
            "петдесет", "шестдесет", "седемдесет", "осемдесет", "деветдесет"]
_BG_HUNDREDS = ["", "сто", "двеста", "триста", "четиристотин",
                "петстотин", "шестстотин", "седемстотин", "осемстотин", "деветстотин"]


def _en_low(n: int) -> str:
    """English words for 0..99; empty for 0 so the hundreds branch can drop it."""
    if n == 0:
        return ""
    if n < 10:
        return _EN_ONES[n]
    if n < 20:
        return _EN_TEENS[n - 10]
    if n % 10 == 0:
        return _EN_TENS[n // 10]
    return f"{_EN_TENS[n // 10]}-{_EN_ONES[n % 10]}"


def _en_words(value: int) -> str:
    if value == 0:
        return _EN_ONES[0]
    hundreds, low = value // 100, _en_low(value % 100)
    if hundreds == 0:
        return low
    if not low:
        return f"{_EN_ONES[hundreds]} hundred"
    return f"{_EN_ONES[hundreds]} hundred {low}"


def _bg_low(n: int) -> str:
    """Bulgarian words for 0..99; empty for 0 so the hundreds branch can drop it."""
    if n == 0:
        return ""
    if n < 10:
        return _BG_ONES[n]
    if n < 20:
        return _BG_TEENS[n - 10]
    if n % 10 == 0:
        return _BG_TENS[n // 10]
    return f"{_BG_TENS[n // 10]} и {_BG_ONES[n % 10]}"


def _bg_words(value: int) -> str:
    if value == 0:
        return _BG_ONES[0]
    hundreds, low = value // 100, _bg_low(value % 100)
    if hundreds == 0:
        return low
    if not low:
        return _BG_HUNDREDS[hundreds]
    # "и" precedes the final atom: glue with " и " when the low part is a single
    # token (сто и пет / сто и двадесет), but a plain space once it already carries
    # its own "и" (сто двадесет и пет).
    if " и " in low:
        return f"{_BG_HUNDREDS[hundreds]} {low}"
    return f"{_BG_HUNDREDS[hundreds]} и {low}"


def words(value: int, bulgarian: bool) -> str:
    """Spell `value` into Bulgarian/English words, or its digit string if out of 0..999."""
    if not 0 <= value <= 999:
        return str(value)
    return _bg_words(value) if bulgarian else _en_words(value)
