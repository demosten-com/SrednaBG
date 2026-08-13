// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation

/// Backend host configuration. Both debug and release builds use the
/// production host so dev work always exercises real zone data; tests
/// construct their own `BackendURLs(baseURL:)` against `MockURLProtocol`.
/// Keep in sync with the Android `BuildConfig.ZONE_API_BASE_URL`.
public struct BackendURLs: Sendable {
    public let baseURL: URL

    public init(baseURL: URL) { self.baseURL = baseURL }

    /// Production host (Namecheap shared hosting).
    public static let production = BackendURLs(
        baseURL: URL(string: "https://srednabg.com")!
    )

    /// Zone-data feed this build is compiled against.
    ///
    /// A feed is a served payload variant: feed 1 is `/api/zones` +
    /// `/api/version` and the unsuffixed `backend/data/zones.json`; feed N>1 is
    /// `/api/zones.N` and `zones.N.json`. The choice is compile-time and never
    /// negotiated — a client only ever fetches its own feed, which is precisely
    /// what lets the backend serve a shape or a zone set older releases could
    /// not parse.
    ///
    /// Bump only alongside a matching entry in `scrapers/contracts/manifest.json`
    /// and a Feed row in `VERSIONS.md`. Keep in sync with the Android
    /// `BuildConfig.ZONE_FEED_VERSION`; the `Bundled Zones` Run Script phase
    /// parses this literal to pick which `zones*.json` to bundle, so it must
    /// stay a plain integer literal on one line.
    public static let feedVersion = 1

    /// Path for `name` on `feed`: `api/zones` on feed 1, `api/zones.N` beyond.
    ///
    /// Feed 1 carrying no suffix is the compatibility promise — every install
    /// ever published fetches `/api/zones`, and that URL must keep resolving.
    /// Kept a pure function of `feed` rather than reading `feedVersion`
    /// directly so the rule is testable for a feed this build isn't compiled
    /// against; pointing a build at the wrong feed is silent, and the data it
    /// then syncs looks perfectly valid. Kotlin twin: `ZoneApi.endpointPath`.
    static func endpointPath(_ name: String, feed: Int) -> String {
        feed == 1 ? "api/\(name)" : "api/\(name).\(feed)"
    }

    public var versionURL: URL {
        baseURL.appendingPathComponent(Self.endpointPath("version", feed: Self.feedVersion))
    }
    public var zonesURL: URL {
        baseURL.appendingPathComponent(Self.endpointPath("zones", feed: Self.feedVersion))
    }
    public var mapBundleURL: URL { baseURL.appendingPathComponent("api/map/bundle.zip") }

    /// Network-served MapLibre style used when the offline bundle hasn't
    /// been installed yet (first-launch race, missing `OfflineMap/` Run
    /// Script, or corrupted bundle). Shape matches `tileserver-gl`'s
    /// `/styles/<id>/style.json` endpoint from `backend/scripts/build-map-bundle.sh`.
    public var mapStyleFallbackURL: URL {
        baseURL.appendingPathComponent("styles/basic-preview/style.json")
    }
}
