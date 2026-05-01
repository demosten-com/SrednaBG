// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore

/// Mirrors `VersionResponse` in `android/.../data/remote/ZoneApi.kt`. The
/// backend emits snake_case; we decode with `.convertFromSnakeCase`.
public struct VersionResponse: Sendable, Codable, Equatable {
    public let version: String
    public let hash: String
    public let minAppVersion: String?
    public let zoneCount: Int?
    public let mapHash: String?

    public init(
        version: String,
        hash: String,
        minAppVersion: String? = nil,
        zoneCount: Int? = nil,
        mapHash: String? = nil
    ) {
        self.version = version
        self.hash = hash
        self.minAppVersion = minAppVersion
        self.zoneCount = zoneCount
        self.mapHash = mapHash
    }
}

/// Mirrors `ZonesResponse` in `android/.../data/remote/ZoneApi.kt`. The
/// `zones` array is the same wire shape as `core.Zone` / Swift `Zone`.
public struct ZonesResponse: Sendable, Codable, Equatable {
    public let version: String
    public let hash: String
    public let zones: [Zone]

    public init(version: String, hash: String, zones: [Zone]) {
        self.version = version
        self.hash = hash
        self.zones = zones
    }
}
