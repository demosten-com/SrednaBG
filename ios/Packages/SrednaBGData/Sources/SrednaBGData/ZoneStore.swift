// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore

/// Actor-isolated zone cache. Holds the active zone list in memory (≤100
/// zones, used per GPS tick) and persists it to JSON on disk so a process
/// restart resumes with the last-synced data without a network round-trip.
///
/// Deliberately not SwiftData: the dataset is tiny, read-heavy with no query
/// dimension, and SwiftData's `ModelContext` isolation rules are ergonomically
/// awkward when the read site is a 1 Hz GPS loop. A plain `[Zone]` cached in
/// this actor is faster, simpler, and unit-testable on macOS.
///
/// On-disk shape: this store persists and decodes a **bare `[Zone]` array**,
/// NOT the `ZonesResponse` wrapper that `BundledZonesLoader` reads from the
/// bundled `bundled-zones.json`. The two files happen to share the
/// "zones.json" base name but are not interchangeable — pointing this store at
/// the bundled asset would decode-fail and silently yield `zones = []`.
public actor ZoneStore {
    private let url: URL
    private(set) var zones: [Zone] = []

    public init(url: URL) {
        self.url = url
    }

    /// Convenience: store under the user's `Application Support` directory.
    /// On iOS this resolves under the app sandbox; on macOS / `swift test`
    /// it lives under `~/Library/Application Support/`.
    public static func defaultURL(fileManager: FileManager = .default) throws -> URL {
        let dir = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        return dir.appendingPathComponent("SrednaBG/zones.json")
    }

    public func loadFromDisk() async {
        guard FileManager.default.fileExists(atPath: url.path) else { return }
        do {
            let data = try Data(contentsOf: url)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            zones = try decoder.decode([Zone].self, from: data)
        } catch {
            // Corrupt cache — drop it. Next sync will repopulate.
            zones = []
            try? FileManager.default.removeItem(at: url)
        }
    }

    public func replaceAll(with newZones: [Zone]) async throws {
        zones = newZones
        try await persist()
    }

    public func snapshot() -> [Zone] {
        zones
    }

    public func count() -> Int {
        zones.count
    }

    private func persist() async throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(zones)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        // `.atomic` already does the temp-file + rename dance — unlike a
        // manual remove-then-move there is no instant where `zones.json`
        // doesn't exist on disk.
        try data.write(to: url, options: .atomic)
    }
}
