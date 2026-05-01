// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

public struct ZoneEndpoint: Sendable, Equatable, Hashable, Codable {
    public let lat: Double
    public let lng: Double
    public let kmMarker: String?
    public let settlement: String?
    public let settlementLatin: String?

    public init(
        lat: Double,
        lng: Double,
        kmMarker: String? = nil,
        settlement: String? = nil,
        settlementLatin: String? = nil
    ) {
        self.lat = lat
        self.lng = lng
        self.kmMarker = kmMarker
        self.settlement = settlement
        self.settlementLatin = settlementLatin
    }
}

public struct SpeedLimits: Sendable, Equatable, Hashable, Codable {
    public let car: Int
    public let truck: Int
    public let bus: Int
    public let motorcycle: Int?

    public init(car: Int, truck: Int, bus: Int, motorcycle: Int? = nil) {
        self.car = car
        self.truck = truck
        self.bus = bus
        self.motorcycle = motorcycle
    }
}

public struct Zone: Sendable, Equatable, Hashable, Codable, Identifiable {
    public let id: String
    public let road: String
    public let roadLatin: String?
    public let direction: String
    public let description: String
    public let start: ZoneEndpoint
    public let end: ZoneEndpoint
    public let distanceM: Int
    public let speedLimits: SpeedLimits
    public let centerline: [[Double]]
    public let source: String
    public let lastVerified: String

    public init(
        id: String,
        road: String,
        roadLatin: String? = nil,
        direction: String,
        description: String,
        start: ZoneEndpoint,
        end: ZoneEndpoint,
        distanceM: Int,
        speedLimits: SpeedLimits,
        centerline: [[Double]],
        source: String,
        lastVerified: String
    ) {
        self.id = id
        self.road = road
        self.roadLatin = roadLatin
        self.direction = direction
        self.description = description
        self.start = start
        self.end = end
        self.distanceM = distanceM
        self.speedLimits = speedLimits
        self.centerline = centerline
        self.source = source
        self.lastVerified = lastVerified
    }
}

public struct GpsPoint: Sendable, Equatable, Hashable {
    public let lat: Double
    public let lng: Double
    public let speed: Double
    public let timestamp: Int64
    public let bearing: Double
    public let accuracy: Double?

    public init(
        lat: Double,
        lng: Double,
        speed: Double,
        timestamp: Int64,
        bearing: Double,
        accuracy: Double? = nil
    ) {
        self.lat = lat
        self.lng = lng
        self.speed = speed
        self.timestamp = timestamp
        self.bearing = bearing
        self.accuracy = accuracy
    }

    public func with(
        lat: Double? = nil,
        lng: Double? = nil,
        speed: Double? = nil,
        timestamp: Int64? = nil,
        bearing: Double? = nil,
        accuracy: Double?? = nil
    ) -> GpsPoint {
        GpsPoint(
            lat: lat ?? self.lat,
            lng: lng ?? self.lng,
            speed: speed ?? self.speed,
            timestamp: timestamp ?? self.timestamp,
            bearing: bearing ?? self.bearing,
            accuracy: accuracy ?? self.accuracy
        )
    }
}

public struct SpeedStatus: Sendable, Equatable, Hashable {
    public let avgSpeed: Double?
    public let maxSpeedForRemainder: Double
    public let distanceRemaining: Double
    public let timeRemaining: Double
    public let isOverLimit: Bool

    public init(
        avgSpeed: Double?,
        maxSpeedForRemainder: Double,
        distanceRemaining: Double,
        timeRemaining: Double,
        isOverLimit: Bool
    ) {
        self.avgSpeed = avgSpeed
        self.maxSpeedForRemainder = maxSpeedForRemainder
        self.distanceRemaining = distanceRemaining
        self.timeRemaining = timeRemaining
        self.isOverLimit = isOverLimit
    }
}

public enum ZoneState: Sendable, Equatable, Hashable {
    case outside
    case inZone(InZone)
    case exiting(Exiting)

    public struct InZone: Sendable, Equatable, Hashable {
        public let zone: Zone
        public let entryTime: Int64
        public let distanceTraveled: Double
        public let avgSpeed: Double?
        public let speedStatus: SpeedStatus
        public let distanceRemaining: Double

        public init(
            zone: Zone,
            entryTime: Int64,
            distanceTraveled: Double,
            avgSpeed: Double?,
            speedStatus: SpeedStatus,
            distanceRemaining: Double
        ) {
            self.zone = zone
            self.entryTime = entryTime
            self.distanceTraveled = distanceTraveled
            self.avgSpeed = avgSpeed
            self.speedStatus = speedStatus
            self.distanceRemaining = distanceRemaining
        }
    }

    public struct Exiting: Sendable, Equatable, Hashable {
        public let zone: Zone
        public let finalAvgSpeed: Double?

        public init(zone: Zone, finalAvgSpeed: Double?) {
            self.zone = zone
            self.finalAvgSpeed = finalAvgSpeed
        }
    }
}
