// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.Zone

/**
 * Last line of defence between `/api/zones` (or a bundled zones.json) and the
 * rest of the app. The scraper's publish guard is the real fix for bad data,
 * but a released client cannot be re-shipped when the server serves something
 * it didn't expect — so anything unusable is dropped *here*, per zone, instead
 * of being allowed to take the whole catalog down with it.
 *
 * The failure this was written for (2026-08): a section on Път I-8 failed to
 * merge upstream and published twice — once with `(0, 0)` endpoints and an
 * empty centerline, once with only a `car` speed limit. Two zero-point
 * LineStrings made MapLibre reject the *entire* zone FeatureCollection
 * ("A line string must have two or more coordinate points"), so all 76 zones
 * vanished from the map. One bad zone must cost one zone, never all of them.
 *
 * Swift twin: `ios/Packages/SrednaBGData/Sources/SrednaBGData/ZoneSanitizer.swift`
 * — keep the rules identical.
 */
object ZoneSanitizer {

    /** A zone the engine could never detect and the map could never draw. */
    fun isUsable(zone: Zone): Boolean {
        if (zone.centerline.count { it.size >= 2 } < 2) return false
        if (zone.start.lat == 0.0 && zone.start.lng == 0.0) return false
        if (zone.end.lat == 0.0 && zone.end.lng == 0.0) return false
        if (zone.distanceM <= 0) return false
        if (zone.speedLimits.car <= 0) return false
        return true
    }

    /**
     * Fill in per-vehicle limits the payload omitted. Gson leaves a missing
     * `truck`/`bus` as `0`, which would read as a 0 km/h limit — instantly and
     * permanently "over limit" for that driver. The schema already treats the
     * car limit as the fallback for a vehicle class a zone doesn't name (the
     * documented rule for `motorcycle`); applying it to truck/bus too keeps a
     * partially-populated zone usable instead of dangerous.
     */
    fun withFallbackLimits(zone: Zone): Zone {
        val limits = zone.speedLimits
        if (limits.truck > 0 && limits.bus > 0) return zone
        return zone.copy(
            speedLimits = SpeedLimits(
                car = limits.car,
                truck = if (limits.truck > 0) limits.truck else limits.car,
                bus = if (limits.bus > 0) limits.bus else limits.car,
                motorcycle = limits.motorcycle,
            ),
        )
    }

    /**
     * Sanitize a freshly parsed catalog. Returns the usable zones (normalized)
     * plus the ids that were dropped, so the caller can log them — a zone
     * silently disappearing is exactly the failure mode this class exists to
     * make visible.
     */
    fun sanitize(zones: List<Zone>): Result {
        val kept = mutableListOf<Zone>()
        val dropped = mutableListOf<String>()
        val repaired = mutableListOf<String>()
        for (zone in zones) {
            if (!isUsable(zone)) {
                dropped += zone.id
                continue
            }
            val fixed = withFallbackLimits(zone)
            if (fixed !== zone) repaired += zone.id
            kept += fixed
        }
        return Result(kept, dropped, repaired)
    }

    /**
     * @property droppedIds zones the app refused outright.
     * @property repairedIds zones it kept only by substituting a missing
     *   truck/bus limit. Reported separately because a repair here is a
     *   *fleet-level* defect elsewhere: the shipped 1.x clients have no such
     *   fallback, and on iOS 1.x the same payload fails the whole
     *   `/api/zones` decode. A silent repair would let QA on a current build
     *   pass on data that is bricking every published install.
     */
    data class Result(
        val zones: List<Zone>,
        val droppedIds: List<String>,
        val repairedIds: List<String> = emptyList(),
    )
}
