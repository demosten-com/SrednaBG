// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

private let earthRadiusM = 6_371_000.0

@inlinable
func toRadians(_ degrees: Double) -> Double { degrees * .pi / 180.0 }

@inlinable
func toDegrees(_ radians: Double) -> Double { radians * 180.0 / .pi }

public func haversineDistance(_ lat1: Double, _ lng1: Double, _ lat2: Double, _ lng2: Double) -> Double {
    let lat1R = toRadians(lat1)
    let lat2R = toRadians(lat2)
    let dLat = toRadians(lat2 - lat1)
    let dLng = toRadians(lng2 - lng1)
    let a = sin(dLat / 2) * sin(dLat / 2)
        + cos(lat1R) * cos(lat2R) * sin(dLng / 2) * sin(dLng / 2)
    return earthRadiusM * 2 * atan2(sqrt(a), sqrt(1 - a))
}

public func pointToSegmentDistance(
    pLat: Double, pLng: Double,
    aLat: Double, aLng: Double,
    bLat: Double, bLng: Double
) -> Double {
    // Flat-earth projection with cos(lat) correction for longitude.
    let midLat = toRadians((aLat + bLat) / 2)
    let cosLat = cos(midLat)
    let metersPerDegLat = 111_320.0
    let metersPerDegLng = 111_320.0 * cosLat

    let bx = (bLng - aLng) * metersPerDegLng
    let by = (bLat - aLat) * metersPerDegLat
    let px = (pLng - aLng) * metersPerDegLng
    let py = (pLat - aLat) * metersPerDegLat

    let abLenSq = bx * bx + by * by
    if abLenSq < 1e-10 {
        return haversineDistance(pLat, pLng, aLat, aLng)
    }

    let t = min(max((px * bx + py * by) / abLenSq, 0.0), 1.0)
    let projLng = aLng + t * (bLng - aLng)
    let projLat = aLat + t * (bLat - aLat)

    return haversineDistance(pLat, pLng, projLat, projLng)
}

public func pointToPolylineDistance(_ lat: Double, _ lng: Double, _ polyline: [[Double]]) -> Double {
    if polyline.isEmpty { return .greatestFiniteMagnitude }
    if polyline.count == 1 {
        return haversineDistance(lat, lng, polyline[0][0], polyline[0][1])
    }
    var minDist = Double.greatestFiniteMagnitude
    for i in 0..<(polyline.count - 1) {
        let d = pointToSegmentDistance(
            pLat: lat, pLng: lng,
            aLat: polyline[i][0], aLng: polyline[i][1],
            bLat: polyline[i + 1][0], bLng: polyline[i + 1][1]
        )
        if d < minDist { minDist = d }
    }
    return minDist
}

public func snapToZone(_ pos: GpsPoint?, state: ZoneState) -> GpsPoint? {
    guard let pos else { return nil }
    guard case .inZone(let inZone) = state else { return pos }
    guard let proj = projectPointOntoPolyline(pos.lat, pos.lng, inZone.zone.centerline) else { return pos }
    return pos.with(lat: proj.lat, lng: proj.lng, bearing: proj.bearing)
}

public struct PolylineProjection: Sendable, Equatable, Hashable {
    public let lat: Double
    public let lng: Double
    public let bearing: Double
    public let distanceFromLineM: Double

    public init(lat: Double, lng: Double, bearing: Double, distanceFromLineM: Double) {
        self.lat = lat
        self.lng = lng
        self.bearing = bearing
        self.distanceFromLineM = distanceFromLineM
    }
}

public func projectPointOntoPolyline(
    _ lat: Double,
    _ lng: Double,
    _ polyline: [[Double]]
) -> PolylineProjection? {
    if polyline.count < 2 { return nil }

    var bestDist = Double.greatestFiniteMagnitude
    var bestLat = 0.0
    var bestLng = 0.0
    var bestSegA: [Double] = polyline[0]
    var bestSegB: [Double] = polyline[1]

    for i in 0..<(polyline.count - 1) {
        let aLat = polyline[i][0]
        let aLng = polyline[i][1]
        let bLat = polyline[i + 1][0]
        let bLng = polyline[i + 1][1]

        let midLat = toRadians((aLat + bLat) / 2)
        let cosLat = cos(midLat)
        let mLat = 111_320.0
        let mLng = 111_320.0 * cosLat

        let bx = (bLng - aLng) * mLng
        let by = (bLat - aLat) * mLat
        let px = (lng - aLng) * mLng
        let py = (lat - aLat) * mLat

        let abLenSq = bx * bx + by * by
        let t: Double = abLenSq < 1e-10 ? 0.0 : min(max((px * bx + py * by) / abLenSq, 0.0), 1.0)

        let projLat = aLat + t * (bLat - aLat)
        let projLng = aLng + t * (bLng - aLng)
        let d = haversineDistance(lat, lng, projLat, projLng)

        if d < bestDist {
            bestDist = d
            bestLat = projLat
            bestLng = projLng
            bestSegA = polyline[i]
            bestSegB = polyline[i + 1]
        }
    }

    let bearing = bearingBetween(bestSegA[0], bestSegA[1], bestSegB[0], bestSegB[1])
    return PolylineProjection(lat: bestLat, lng: bestLng, bearing: bearing, distanceFromLineM: bestDist)
}

public func projectOntoPolyline(_ lat: Double, _ lng: Double, _ polyline: [[Double]]) -> Double {
    if polyline.count < 2 { return 0.0 }

    var bestDist = Double.greatestFiniteMagnitude
    var bestCumulative = 0.0
    var cumulative = 0.0

    for i in 0..<(polyline.count - 1) {
        let aLat = polyline[i][0]
        let aLng = polyline[i][1]
        let bLat = polyline[i + 1][0]
        let bLng = polyline[i + 1][1]

        let segLen = haversineDistance(aLat, aLng, bLat, bLng)

        let midLat = toRadians((aLat + bLat) / 2)
        let cosLat = cos(midLat)
        let mLat = 111_320.0
        let mLng = 111_320.0 * cosLat

        let bx = (bLng - aLng) * mLng
        let by = (bLat - aLat) * mLat
        let px = (lng - aLng) * mLng
        let py = (lat - aLat) * mLat

        let abLenSq = bx * bx + by * by
        let t: Double = abLenSq < 1e-10 ? 0.0 : min(max((px * bx + py * by) / abLenSq, 0.0), 1.0)

        let projLat = aLat + t * (bLat - aLat)
        let projLng = aLng + t * (bLng - aLng)
        let d = haversineDistance(lat, lng, projLat, projLng)

        if d < bestDist {
            bestDist = d
            bestCumulative = cumulative + t * segLen
        }

        cumulative += segLen
    }
    return bestCumulative
}

public func bearingBetween(_ lat1: Double, _ lng1: Double, _ lat2: Double, _ lng2: Double) -> Double {
    let lat1R = toRadians(lat1)
    let lat2R = toRadians(lat2)
    let dLng = toRadians(lng2 - lng1)
    let x = sin(dLng) * cos(lat2R)
    let y = cos(lat1R) * sin(lat2R) - sin(lat1R) * cos(lat2R) * cos(dLng)
    let bearing = toDegrees(atan2(x, y))
    return (bearing + 360).truncatingRemainder(dividingBy: 360)
}

public func bearingDifference(_ b1: Double, _ b2: Double) -> Double {
    let diff = abs(b1 - b2).truncatingRemainder(dividingBy: 360)
    return diff > 180 ? 360 - diff : diff
}

/// Returns nil for unknown direction strings — callers fall back to the
/// polyline-derived bearing when this is not one of the four cardinals.
public func directionToBearing(_ direction: String) -> Double? {
    switch direction {
    case "north": return 0
    case "east": return 90
    case "south": return 180
    case "west": return 270
    default: return nil
    }
}

/// Returns nil for polylines with fewer than 2 points.
public func polylineBearing(_ polyline: [[Double]]) -> Double? {
    guard polyline.count >= 2,
          let first = polyline.first,
          let last = polyline.last
    else { return nil }
    return bearingBetween(first[0], first[1], last[0], last[1])
}
