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

    public var versionURL: URL { baseURL.appendingPathComponent("api/version") }
    public var zonesURL: URL { baseURL.appendingPathComponent("api/zones") }
    public var mapBundleURL: URL { baseURL.appendingPathComponent("api/map/bundle.zip") }

    /// Network-served MapLibre style used when the offline bundle hasn't
    /// been installed yet (first-launch race, missing `OfflineMap/` Run
    /// Script, or corrupted bundle). Shape matches `tileserver-gl`'s
    /// `/styles/<id>/style.json` endpoint from `backend/scripts/build-map-bundle.sh`.
    public var mapStyleFallbackURL: URL {
        baseURL.appendingPathComponent("styles/basic-preview/style.json")
    }
}
