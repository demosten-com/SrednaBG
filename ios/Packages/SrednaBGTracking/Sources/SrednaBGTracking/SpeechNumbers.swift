// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation

/// Spells an integer speed into words before it is handed to `AVSpeechSynthesizer`, so the
/// engine never falls back to reading a bare number digit-by-digit ("one one two" instead
/// of "one hundred twelve"). Covers the 0...999 range that real speeds occupy; anything
/// outside it returns the plain digit string (lets the engine normalize).
///
/// Hand-port of Android's `SpeechNumbers.kt` (`toWords`) so the two platforms speak
/// byte-identical phrases per language.
enum SpeechNumbers {

    private static let enOnes = [
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"
    ]
    private static let enTeens = [
        "ten", "eleven", "twelve", "thirteen", "fourteen",
        "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"
    ]
    private static let enTens = [
        "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"
    ]

    private static let bgOnes = [
        "нула", "едно", "две", "три", "четири", "пет", "шест", "седем", "осем", "девет"
    ]
    private static let bgTeens = [
        "десет", "единадесет", "дванадесет", "тринадесет", "четиринадесет",
        "петнадесет", "шестнадесет", "седемнадесет", "осемнадесет", "деветнадесет"
    ]
    private static let bgTens = [
        "", "", "двадесет", "тридесет", "четиридесет",
        "петдесет", "шестдесет", "седемдесет", "осемдесет", "деветдесет"
    ]
    private static let bgHundreds = [
        "", "сто", "двеста", "триста", "четиристотин",
        "петстотин", "шестстотин", "седемстотин", "осемстотин", "деветстотин"
    ]

    /// Spell `value` into `bulgarian`/English words, or its digit string if out of 0...999.
    static func words(_ value: Int, bulgarian: Bool) -> String {
        guard (0...999).contains(value) else { return String(value) }
        return bulgarian ? bgWords(value) : enWords(value)
    }

    private static func enWords(_ value: Int) -> String {
        if value == 0 { return enOnes[0] }
        let hundreds = value / 100
        let low = enLow(value % 100)
        if hundreds == 0 { return low }
        if low.isEmpty { return "\(enOnes[hundreds]) hundred" }
        return "\(enOnes[hundreds]) hundred \(low)"
    }

    /// English words for 0...99; empty for 0 so the hundreds branch can drop it.
    private static func enLow(_ n: Int) -> String {
        switch n {
        case 0: return ""
        case 1..<10: return enOnes[n]
        case 10..<20: return enTeens[n - 10]
        case _ where n % 10 == 0: return enTens[n / 10]
        default: return "\(enTens[n / 10])-\(enOnes[n % 10])"
        }
    }

    private static func bgWords(_ value: Int) -> String {
        if value == 0 { return bgOnes[0] }
        let hundreds = value / 100
        let low = bgLow(value % 100)
        if hundreds == 0 { return low }
        if low.isEmpty { return bgHundreds[hundreds] }
        // "и" precedes the final atom: glue with " и " when the low part is a single
        // token (сто и пет / сто и двадесет), but a plain space once it already carries
        // its own "и" (сто двадесет и пет).
        if low.contains(" и ") { return "\(bgHundreds[hundreds]) \(low)" }
        return "\(bgHundreds[hundreds]) и \(low)"
    }

    /// Bulgarian words for 0...99; empty for 0 so the hundreds branch can drop it.
    private static func bgLow(_ n: Int) -> String {
        switch n {
        case 0: return ""
        case 1..<10: return bgOnes[n]
        case 10..<20: return bgTeens[n - 10]
        case _ where n % 10 == 0: return bgTens[n / 10]
        default: return "\(bgTens[n / 10]) и \(bgOnes[n % 10])"
        }
    }
}
