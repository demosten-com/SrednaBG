// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Testing
@testable import SrednaBGData
import SrednaBGCore

@Suite("BundledZonesLoader")
struct BundledZonesLoaderTests {

    @Test
    func loadsBundledFixture() throws {
        let loader = BundledZonesLoader(
            bundle: .module,
            resourceName: "Resources/bundled-zones",
            resourceExtension: "json"
        )
        let response = try #require(loader.load())
        #expect(response.hash == "sha256:fixture")
        #expect(response.zones.count == 1)
        #expect(response.zones[0].id == "trakiya-01-west")
        #expect(response.zones[0].speedLimits.car == 140)
    }

    @Test
    func missingResourceReturnsNil() {
        let loader = BundledZonesLoader(
            bundle: .module,
            resourceName: "does-not-exist",
            resourceExtension: "json"
        )
        #expect(loader.load() == nil)
    }
}
