// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Foundation
import Testing
@testable import SrednaBGUI

@Suite("ZoneDataFormat")
struct ZoneDataFormatTests {

    @Test
    func prefixedHashDropsPrefixAndTakesFirst16() {
        #expect(
            ZoneDataFormat.shortHash("sha256:e344717a5262a59526484fa9f48e68173e84939498f96535997e1c7f8a38644b")
                == "e344717a5262a595"
        )
    }

    @Test
    func unprefixedHashTakesFirst16() {
        #expect(
            ZoneDataFormat.shortHash("e344717a5262a59526484fa9f48e68173e84939498f96535997e1c7f8a38644b")
                == "e344717a5262a595"
        )
    }

    @Test
    func shortHashPassesThrough() {
        #expect(ZoneDataFormat.shortHash("abc123") == "abc123")
    }

    @Test
    func emptyHashRendersAsDash() {
        #expect(ZoneDataFormat.shortHash("") == "--")
    }

    @Test
    func barePrefixRendersAsDash() {
        #expect(ZoneDataFormat.shortHash("sha256:") == "--")
    }

    @Test
    func versionFormatsInShortLocaleStyle() {
        // Time zone is device-local in production; assert on the date parts
        // that survive any zone shift of a 05:32 UTC instant (the day can
        // move at most to the 10th or 12th).
        let formatted = ZoneDataFormat.formatVersion(
            "2026-06-11T05:32:40Z",
            locale: Locale(identifier: "en_US")
        )
        #expect(formatted != "--")
        #expect(formatted.contains("/2026"))
        #expect(formatted.contains(":32"))
    }

    @Test
    func emptyVersionRendersAsDash() {
        #expect(ZoneDataFormat.formatVersion("") == "--")
    }

    @Test
    func unparseableVersionRendersAsDash() {
        #expect(ZoneDataFormat.formatVersion("not-a-date") == "--")
    }
}
