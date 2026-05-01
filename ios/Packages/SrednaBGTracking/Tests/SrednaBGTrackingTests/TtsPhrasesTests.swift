// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Testing
@testable import SrednaBGTracking
import SrednaBGData

@Suite("TtsPhrases")
struct TtsPhrasesTests {

    @Test
    func bgEntryMatchesAndroid() {
        let phrase = TtsPhrases.phrase(for: .entry(road: "АМ Тракия", limit: 140), language: .bg)
        #expect(phrase == "Влизате в зона за средна скорост. Ограничение 140.")
    }

    @Test
    func enEntryMatchesAndroid() {
        let phrase = TtsPhrases.phrase(for: .entry(road: "АМ Тракия", limit: 140), language: .en)
        #expect(phrase == "Entering average speed zone. Speed limit 140.")
    }

    @Test
    func bgOverLimitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .overLimit(avgSpeedKmh: 152), language: .bg)
                == "Внимание: средна скорост 152. Намалете.")
    }

    @Test
    func enOverLimitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .overLimit(avgSpeedKmh: 152), language: .en)
                == "Warning: average speed 152. Slow down.")
    }

    @Test
    func bgRecoveredMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .recovered(avgSpeedKmh: 138), language: .bg)
                == "Средната скорост е отново в норма. 138.")
    }

    @Test
    func enRecoveredMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .recovered(avgSpeedKmh: 138), language: .en)
                == "Back within limit. 138.")
    }

    @Test
    func bgWithinLimitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .withinLimit(avgSpeedKmh: 130), language: .bg)
                == "Средна скорост 130. В норма.")
    }

    @Test
    func enWithinLimitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .withinLimit(avgSpeedKmh: 130), language: .en)
                == "Average speed 130. Within limit.")
    }

    @Test
    func bgExitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .exit(avgSpeedKmh: 132), language: .bg)
                == "Излизате от зоната. Средна скорост 132.")
    }

    @Test
    func enExitMatchesAndroid() {
        #expect(TtsPhrases.phrase(for: .exit(avgSpeedKmh: 132), language: .en)
                == "Leaving zone. Average speed was 132.")
    }
}
