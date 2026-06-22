// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Testing
@testable import SrednaBGTracking
import SrednaBGData

@Suite("TtsPhrases")
struct TtsPhrasesTests {

    // Numbers are spelled into words (see `SpeechNumbers`) so the engine never reads a
    // speed digit-by-digit: 140 → "сто и четиридесет" / "one hundred forty", etc.

    @Test
    func bgEntryMatchesAndroid() {
        let phrase = TtsPhrases.phrase(for: .entry(road: "АМ Тракия", limit: 140), language: .bg)
        #expect(phrase == "Влизате в зона за средна скорост. Ограничение сто и четиридесет.")
    }

    @Test
    func enEntryMatchesAndroid() {
        let phrase = TtsPhrases.phrase(for: .entry(road: "АМ Тракия", limit: 140), language: .en)
        #expect(phrase == "Entering average speed zone. Speed limit one hundred forty.")
    }

    @Test
    func bgOverLimitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .overLimit(avgSpeedKmh: 152), language: .bg)
                == "Внимание: средна скорост сто петдесет и две. Намалете.")
    }

    @Test
    func enOverLimitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .overLimit(avgSpeedKmh: 152), language: .en)
                == "Warning: average speed one hundred fifty-two. Slow down.")
    }

    @Test
    func bgRecoveredMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .recovered(avgSpeedKmh: 138), language: .bg)
                == "Средната скорост е отново в норма. сто тридесет и осем.")
    }

    @Test
    func enRecoveredMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .recovered(avgSpeedKmh: 138), language: .en)
                == "Back within limit. one hundred thirty-eight.")
    }

    @Test
    func bgWithinLimitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .withinLimit(avgSpeedKmh: 130), language: .bg)
                == "Средна скорост сто и тридесет. В норма.")
    }

    @Test
    func enWithinLimitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .withinLimit(avgSpeedKmh: 130), language: .en)
                == "Average speed one hundred thirty. Within limit.")
    }

    @Test
    func bgExitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .exit(avgSpeedKmh: 132), language: .bg)
                == "Излизате от зоната. Средна скорост сто тридесет и две.")
    }

    @Test
    func enExitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .exit(avgSpeedKmh: 132), language: .en)
                == "Leaving zone. Average speed was one hundred thirty-two.")
    }
}
