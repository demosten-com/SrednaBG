// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Testing
@testable import SrednaBGData

/// The data-feed suffix rule.
///
/// Worth pinning because getting it wrong is *silent*: a build pointed at the
/// wrong feed still receives a well-formed payload and syncs it happily, so
/// nothing downstream reports a problem — the user simply gets somebody else's
/// zone data. The feed-1 cases are the load-bearing ones; every install ever
/// published fetches those two bare paths.
@Suite("BackendURLs feed paths")
struct BackendURLsTests {

    private let urls = BackendURLs(baseURL: URL(string: "https://srednabg.com")!)

    @Test
    func feedOneHasNoSuffix() {
        #expect(BackendURLs.endpointPath("zones", feed: 1) == "api/zones")
        #expect(BackendURLs.endpointPath("version", feed: 1) == "api/version")
    }

    @Test
    func laterFeedsAreSuffixed() {
        #expect(BackendURLs.endpointPath("zones", feed: 2) == "api/zones.2")
        #expect(BackendURLs.endpointPath("version", feed: 12) == "api/version.12")
    }

    @Test
    func productionURLsMatchTheCompiledFeed() {
        let suffix = BackendURLs.feedVersion == 1 ? "" : ".\(BackendURLs.feedVersion)"
        #expect(urls.zonesURL.absoluteString == "https://srednabg.com/api/zones\(suffix)")
        #expect(urls.versionURL.absoluteString == "https://srednabg.com/api/version\(suffix)")
    }

    /// The map bundle is not feed-scoped — it carries no zone data, and giving
    /// it a suffix would send every feed chasing a URL the host doesn't serve.
    @Test
    func mapBundleIsNotFeedScoped() {
        #expect(urls.mapBundleURL.absoluteString == "https://srednabg.com/api/map/bundle.zip")
    }

    /// Kept in sync with `scrapers/contracts/manifest.json` and the Feed column
    /// in VERSIONS.md. If this fails, the change was deliberate — update those
    /// two as well, and check `Bundled Zones` still finds `zones.N.json`.
    @Test
    func thisBuildIsOnFeedOne() {
        #expect(BackendURLs.feedVersion == 1)
    }
}
