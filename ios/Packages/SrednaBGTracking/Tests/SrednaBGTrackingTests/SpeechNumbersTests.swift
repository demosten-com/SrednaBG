// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Testing
@testable import SrednaBGTracking

@Suite("SpeechNumbers")
struct SpeechNumbersTests {

    @Test
    func englishSpellsSpeedsAsSingleNumbers() {
        #expect(SpeechNumbers.words(0, bulgarian: false) == "zero")
        #expect(SpeechNumbers.words(5, bulgarian: false) == "five")
        #expect(SpeechNumbers.words(12, bulgarian: false) == "twelve")
        #expect(SpeechNumbers.words(20, bulgarian: false) == "twenty")
        #expect(SpeechNumbers.words(25, bulgarian: false) == "twenty-five")
        #expect(SpeechNumbers.words(90, bulgarian: false) == "ninety")
        #expect(SpeechNumbers.words(100, bulgarian: false) == "one hundred")
        #expect(SpeechNumbers.words(101, bulgarian: false) == "one hundred one")
        #expect(SpeechNumbers.words(112, bulgarian: false) == "one hundred twelve")
        #expect(SpeechNumbers.words(120, bulgarian: false) == "one hundred twenty")
        #expect(SpeechNumbers.words(125, bulgarian: false) == "one hundred twenty-five")
        #expect(SpeechNumbers.words(130, bulgarian: false) == "one hundred thirty")
        #expect(SpeechNumbers.words(140, bulgarian: false) == "one hundred forty")
        #expect(SpeechNumbers.words(152, bulgarian: false) == "one hundred fifty-two")
        #expect(SpeechNumbers.words(160, bulgarian: false) == "one hundred sixty")
        #expect(SpeechNumbers.words(230, bulgarian: false) == "two hundred thirty")
        #expect(SpeechNumbers.words(999, bulgarian: false) == "nine hundred ninety-nine")
    }

    @Test
    func bulgarianSpellsSpeedsWithCorrectConjunction() {
        #expect(SpeechNumbers.words(0, bulgarian: true) == "нула")
        #expect(SpeechNumbers.words(5, bulgarian: true) == "пет")
        #expect(SpeechNumbers.words(12, bulgarian: true) == "дванадесет")
        #expect(SpeechNumbers.words(20, bulgarian: true) == "двадесет")
        #expect(SpeechNumbers.words(25, bulgarian: true) == "двадесет и пет")
        #expect(SpeechNumbers.words(90, bulgarian: true) == "деветдесет")
        #expect(SpeechNumbers.words(95, bulgarian: true) == "деветдесет и пет")
        #expect(SpeechNumbers.words(100, bulgarian: true) == "сто")
        #expect(SpeechNumbers.words(101, bulgarian: true) == "сто и едно")
        #expect(SpeechNumbers.words(105, bulgarian: true) == "сто и пет")
        #expect(SpeechNumbers.words(112, bulgarian: true) == "сто и дванадесет")
        #expect(SpeechNumbers.words(120, bulgarian: true) == "сто и двадесет")
        #expect(SpeechNumbers.words(125, bulgarian: true) == "сто двадесет и пет")
        #expect(SpeechNumbers.words(130, bulgarian: true) == "сто и тридесет")
        #expect(SpeechNumbers.words(140, bulgarian: true) == "сто и четиридесет")
        #expect(SpeechNumbers.words(152, bulgarian: true) == "сто петдесет и две")
        #expect(SpeechNumbers.words(230, bulgarian: true) == "двеста и тридесет")
        #expect(SpeechNumbers.words(999, bulgarian: true) == "деветстотин деветдесет и девет")
    }

    @Test
    func outOfRangeValuesFallBackToDigitString() {
        #expect(SpeechNumbers.words(1000, bulgarian: false) == "1000")
        #expect(SpeechNumbers.words(1000, bulgarian: true) == "1000")
        #expect(SpeechNumbers.words(-5, bulgarian: false) == "-5")
    }
}
