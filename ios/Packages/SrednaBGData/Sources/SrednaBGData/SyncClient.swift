// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore

public enum SyncClientError: Error, Sendable {
    case httpStatus(Int, url: URL)
    case emptyBody(url: URL)
}

/// Wraps `URLSession` for the three backend endpoints (`/api/version`,
/// `/api/zones`, `/api/map/bundle.zip`). Actor-isolated so we never have two
/// concurrent zone-sync requests in flight; the foreground UI's "Sync now"
/// and the background `BGAppRefreshTask` both go through the same instance.
public actor SyncClient {
    public nonisolated let urls: BackendURLs
    private let session: URLSession
    private let decoder: JSONDecoder

    public init(urls: BackendURLs, session: URLSession = .shared) {
        self.urls = urls
        self.session = session
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        self.decoder = decoder
    }

    /// Builds a request that always revalidates against the origin server.
    ///
    /// The backend (LiteSpeed) serves the freshness endpoints with
    /// `Cache-Control: public, max-age=300` on `/api/version` and `max-age=3600`
    /// on `/api/zones`. `URLSession.shared`'s default `.useProtocolCachePolicy`
    /// honors those, so a "Sync zones now" tap within the max-age window would
    /// be served from `URLCache.shared` without a network round-trip — the user
    /// sees an instant "Up to date" and a genuine server-side zone change stays
    /// invisible for up to 5 min. Android's `OkHttpClient` installs no cache, so
    /// this only bit iOS; `.reloadIgnoringLocalCacheData` restores parity.
    private static func freshRequest(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        return request
    }

    public func fetchVersion() async throws -> VersionResponse {
        let data = try await get(urls.versionURL)
        return try decoder.decode(VersionResponse.self, from: data)
    }

    public func fetchZones() async throws -> ZonesResponse {
        let data = try await get(urls.zonesURL)
        return try decoder.decode(ZonesResponse.self, from: data)
    }

    /// Streams the (~50 MB) map bundle to disk. Returns the destination URL.
    /// Caller is responsible for moving / unzipping the file via
    /// `OfflineMapInstaller`.
    public func downloadMapBundle(to destination: URL) async throws -> URL {
        let url = urls.mapBundleURL
        let (tempURL, response) = try await session.download(for: Self.freshRequest(url))
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? -1
            try? FileManager.default.removeItem(at: tempURL)
            throw SyncClientError.httpStatus(code, url: url)
        }
        // Move atomically into the caller-controlled destination.
        let fm = FileManager.default
        if fm.fileExists(atPath: destination.path) {
            try fm.removeItem(at: destination)
        }
        try fm.moveItem(at: tempURL, to: destination)
        return destination
    }

    private func get(_ url: URL) async throws -> Data {
        let (data, response) = try await session.data(for: Self.freshRequest(url))
        guard let http = response as? HTTPURLResponse else {
            throw SyncClientError.emptyBody(url: url)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw SyncClientError.httpStatus(http.statusCode, url: url)
        }
        guard !data.isEmpty else {
            throw SyncClientError.emptyBody(url: url)
        }
        return data
    }
}
