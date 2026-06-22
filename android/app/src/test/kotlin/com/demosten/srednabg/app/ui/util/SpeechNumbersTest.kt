// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class SpeechNumbersTest {

    @Test
    fun `english spells speeds as single numbers`() {
        assertEquals("zero", SpeechNumbers.toWords(0, bulgarian = false))
        assertEquals("five", SpeechNumbers.toWords(5, bulgarian = false))
        assertEquals("twelve", SpeechNumbers.toWords(12, bulgarian = false))
        assertEquals("twenty", SpeechNumbers.toWords(20, bulgarian = false))
        assertEquals("twenty-five", SpeechNumbers.toWords(25, bulgarian = false))
        assertEquals("ninety", SpeechNumbers.toWords(90, bulgarian = false))
        assertEquals("one hundred", SpeechNumbers.toWords(100, bulgarian = false))
        assertEquals("one hundred one", SpeechNumbers.toWords(101, bulgarian = false))
        assertEquals("one hundred twelve", SpeechNumbers.toWords(112, bulgarian = false))
        assertEquals("one hundred twenty", SpeechNumbers.toWords(120, bulgarian = false))
        assertEquals("one hundred twenty-five", SpeechNumbers.toWords(125, bulgarian = false))
        assertEquals("one hundred thirty", SpeechNumbers.toWords(130, bulgarian = false))
        assertEquals("one hundred forty", SpeechNumbers.toWords(140, bulgarian = false))
        assertEquals("one hundred sixty", SpeechNumbers.toWords(160, bulgarian = false))
        assertEquals("nine hundred ninety-nine", SpeechNumbers.toWords(999, bulgarian = false))
    }

    @Test
    fun `bulgarian spells speeds with correct conjunction placement`() {
        assertEquals("нула", SpeechNumbers.toWords(0, bulgarian = true))
        assertEquals("пет", SpeechNumbers.toWords(5, bulgarian = true))
        assertEquals("дванадесет", SpeechNumbers.toWords(12, bulgarian = true))
        assertEquals("двадесет", SpeechNumbers.toWords(20, bulgarian = true))
        assertEquals("двадесет и пет", SpeechNumbers.toWords(25, bulgarian = true))
        assertEquals("деветдесет", SpeechNumbers.toWords(90, bulgarian = true))
        assertEquals("деветдесет и пет", SpeechNumbers.toWords(95, bulgarian = true))
        assertEquals("сто", SpeechNumbers.toWords(100, bulgarian = true))
        assertEquals("сто и едно", SpeechNumbers.toWords(101, bulgarian = true))
        assertEquals("сто и пет", SpeechNumbers.toWords(105, bulgarian = true))
        assertEquals("сто и дванадесет", SpeechNumbers.toWords(112, bulgarian = true))
        assertEquals("сто и двадесет", SpeechNumbers.toWords(120, bulgarian = true))
        assertEquals("сто двадесет и пет", SpeechNumbers.toWords(125, bulgarian = true))
        assertEquals("сто и тридесет", SpeechNumbers.toWords(130, bulgarian = true))
        assertEquals("сто четиридесет и пет", SpeechNumbers.toWords(145, bulgarian = true))
        assertEquals("двеста и тридесет", SpeechNumbers.toWords(230, bulgarian = true))
    }

    @Test
    fun `out of range values fall back to digit string`() {
        assertEquals("1000", SpeechNumbers.toWords(1000, bulgarian = false))
        assertEquals("1000", SpeechNumbers.toWords(1000, bulgarian = true))
        assertEquals("-5", SpeechNumbers.toWords(-5, bulgarian = false))
    }
}
