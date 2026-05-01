// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Testing
import SwiftUI
@testable import SrednaBGUI
import SrednaBGCore

@Suite("Theme")
struct ThemeTests {

    @Test
    func packedColorBridgeReturnsExpectedSwiftColors() {
        // Sanity check that the Int32 → Color mapping covers the three core
        // status colors. Equality on `Color` is structural — the underlying
        // RGB triplet matches our hex-derived constants exactly.
        #expect(statusSwiftUIColor(zoneColorGreen) == Theme.statusGreen)
        #expect(statusSwiftUIColor(zoneColorYellow) == Theme.statusAmber)
        #expect(statusSwiftUIColor(zoneColorRed) == Theme.statusRed)
    }

    @Test
    func unknownColorFallsBackToPrimary() {
        #expect(statusSwiftUIColor(0) == .primary)
    }
}
