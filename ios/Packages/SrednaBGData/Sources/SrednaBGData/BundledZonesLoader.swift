// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore

/// Loads the bundled `bundled-zones.json` shipped in the app's main bundle so
/// the first launch has zones to work with even before `/api/zones` succeeds.
/// Returns nil — never throws — if the asset is missing or malformed: the
/// `Failed` SyncResult path will surface the missing data the next time the
/// network sync runs.
public struct BundledZonesLoader: Sendable {
    private let bundle: Bundle
    private let resourceName: String
    private let resourceExtension: String

    public init(
        bundle: Bundle = .main,
        resourceName: String = "bundled-zones",
        resourceExtension: String = "json"
    ) {
        self.bundle = bundle
        self.resourceName = resourceName
        self.resourceExtension = resourceExtension
    }

    public func load() -> ZonesResponse? {
        guard let url = bundle.url(forResource: resourceName, withExtension: resourceExtension) else {
            return nil
        }
        do {
            let data = try Data(contentsOf: url)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(ZonesResponse.self, from: data)
        } catch {
            // A malformed bundled asset would otherwise leave the user on an
            // empty map with no diagnostic. Log before falling back to nil
            // (the next network sync still repopulates). Mirrors Android's
            // `loadFromAssets` `Log.w` on decode failure.
            QALog.location.error("bundled-zones decode failed: \(String(describing: error), privacy: .public)")
            return nil
        }
    }
}
