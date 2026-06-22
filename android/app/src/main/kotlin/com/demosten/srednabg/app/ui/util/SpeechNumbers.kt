// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

/**
 * Spells an integer speed into words before it is handed to TextToSpeech, so the
 * engine never falls back to reading a bare number digit-by-digit ("one one two"
 * instead of "one hundred twelve"). Covers the 0..999 range that real speeds occupy;
 * anything outside it returns the plain digit string (lets the engine normalize).
 */
object SpeechNumbers {

    private val EN_ONES = listOf(
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    )
    private val EN_TEENS = listOf(
        "ten", "eleven", "twelve", "thirteen", "fourteen",
        "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
    )
    private val EN_TENS = listOf(
        "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    )

    private val BG_ONES = listOf(
        "нула", "едно", "две", "три", "четири", "пет", "шест", "седем", "осем", "девет",
    )
    private val BG_TEENS = listOf(
        "десет", "единадесет", "дванадесет", "тринадесет", "четиринадесет",
        "петнадесет", "шестнадесет", "седемнадесет", "осемнадесет", "деветнадесет",
    )
    private val BG_TENS = listOf(
        "", "", "двадесет", "тридесет", "четиридесет",
        "петдесет", "шестдесет", "седемдесет", "осемдесет", "деветдесет",
    )
    private val BG_HUNDREDS = listOf(
        "", "сто", "двеста", "триста", "четиристотин",
        "петстотин", "шестстотин", "седемстотин", "осемстотин", "деветстотин",
    )

    /** Spell [value] into [bulgarian]/English words, or its digit string if out of 0..999. */
    fun toWords(value: Int, bulgarian: Boolean): String {
        if (value !in 0..999) return value.toString()
        return if (bulgarian) bgWords(value) else enWords(value)
    }

    private fun enWords(value: Int): String {
        if (value == 0) return EN_ONES[0]
        val hundreds = value / 100
        val low = enLow(value % 100)
        return when {
            hundreds == 0 -> low
            low.isEmpty() -> "${EN_ONES[hundreds]} hundred"
            else -> "${EN_ONES[hundreds]} hundred $low"
        }
    }

    /** English words for 0..99; empty for 0 so the hundreds branch can drop it. */
    private fun enLow(n: Int): String = when {
        n == 0 -> ""
        n < 10 -> EN_ONES[n]
        n < 20 -> EN_TEENS[n - 10]
        n % 10 == 0 -> EN_TENS[n / 10]
        else -> "${EN_TENS[n / 10]}-${EN_ONES[n % 10]}"
    }

    private fun bgWords(value: Int): String {
        if (value == 0) return BG_ONES[0]
        val hundreds = value / 100
        val low = bgLow(value % 100)
        return when {
            hundreds == 0 -> low
            low.isEmpty() -> BG_HUNDREDS[hundreds]
            // "и" precedes the final atom: glue with " и " when the low part is a single
            // token (сто и пет / сто и двадесет), but a plain space once it already carries
            // its own "и" (сто двадесет и пет).
            low.contains(" и ") -> "${BG_HUNDREDS[hundreds]} $low"
            else -> "${BG_HUNDREDS[hundreds]} и $low"
        }
    }

    /** Bulgarian words for 0..99; empty for 0 so the hundreds branch can drop it. */
    private fun bgLow(n: Int): String = when {
        n == 0 -> ""
        n < 10 -> BG_ONES[n]
        n < 20 -> BG_TEENS[n - 10]
        n % 10 == 0 -> BG_TENS[n / 10]
        else -> "${BG_TENS[n / 10]} и ${BG_ONES[n % 10]}"
    }
}
