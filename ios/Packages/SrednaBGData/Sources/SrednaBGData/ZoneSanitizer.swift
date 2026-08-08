// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore

/// Last line of defence between `/api/zones` (or `bundled-zones.json`) and the
/// rest of the app. The scraper's publish guard is the real fix for bad data,
/// but a released client can't be re-shipped when the server serves something
/// it didn't expect — so anything unusable is dropped *here*, per zone, rather
/// than being allowed to take the whole catalog down with it.
///
/// The failure this was written for (2026-08): a section on Път I-8 failed to
/// merge upstream and published twice — once with `(0, 0)` endpoints and an
/// empty centerline, once with only a `car` speed limit. On Android two
/// zero-point LineStrings made MapLibre reject the entire zone
/// FeatureCollection, blanking all 76 zones on the map. One bad zone must cost
/// one zone, never all of them.
///
/// Kotlin twin: `android/.../app/data/ZoneSanitizer.kt` — keep the rules
/// identical.
public enum ZoneSanitizer {

    /// A zone the engine could never detect and the map could never draw.
    public static func isUsable(_ zone: Zone) -> Bool {
        guard zone.centerline.filter({ $0.count >= 2 }).count >= 2 else { return false }
        guard !(zone.start.lat == 0 && zone.start.lng == 0) else { return false }
        guard !(zone.end.lat == 0 && zone.end.lng == 0) else { return false }
        guard zone.distanceM > 0 else { return false }
        guard zone.speedLimits.car > 0 else { return false }
        return true
    }

    /// The usable subset, the ids that were dropped, and the ids that survived
    /// only because a limit was repaired.
    ///
    /// Both lists must be logged. A dropped zone vanishes between the wire and
    /// the map; a **repaired** one looks perfectly healthy here and is fatal in
    /// the field — the 1.x clients in the stores have no such fallback, and on
    /// iOS 1.x that payload fails the entire `/api/zones` decode. Without
    /// surfacing repairs, QA on a current build passes on data that is bricking
    /// every published install.
    ///
    /// The repair itself happens in `SpeedLimits`' decoder (it has to — a
    /// missing key would otherwise throw before this code ever runs), so this
    /// only reads the flag it left behind.
    public static func sanitize(
        _ zones: [Zone]
    ) -> (zones: [Zone], droppedIds: [String], repairedIds: [String]) {
        var kept: [Zone] = []
        var dropped: [String] = []
        var repaired: [String] = []
        for zone in zones {
            guard isUsable(zone) else {
                dropped.append(zone.id)
                continue
            }
            if zone.speedLimits.didFallBackToCarLimit {
                repaired.append(zone.id)
            }
            kept.append(zone)
        }
        return (kept, dropped, repaired)
    }
}
