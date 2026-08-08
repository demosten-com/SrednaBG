// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.debug

import com.demosten.srednabg.app.data.HistoryRepository
import com.demosten.srednabg.app.data.local.ZoneTraversalEntity
import com.demosten.srednabg.app.data.local.toSamplesJson
import com.demosten.srednabg.core.HistoryStats
import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.SpeedSample
import com.demosten.srednabg.core.VehicleType
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import com.google.gson.Gson
import java.time.Instant
import java.time.ZoneId
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Debug-only: fills the History DB with a curated, deterministic set of varied
 * [ZoneTraversalEntity] records so a developer can launch the app and browse
 * realistic scenarios — within-limit vs over-limit, every vehicle type, short and
 * long traversals, spread across several days — without driving every zone by
 * hand. Reached only through [DebugControlReceiver]'s `SEED_HISTORY` action,
 * which lives in `src/debug/`, so the fabricated data never ships in a release.
 *
 * Hand-port of iOS's `HistorySeeder` (`ios/.../SrednaBGData/HistorySeeder.swift`):
 * same scenario script, same PRNG, same fallback zones, and — crucially — it
 * writes finalized records straight into [HistoryRepository] while computing the
 * exact same sustained-min/max, running-average and downsample stats the real
 * `HistoryRecorder` would, so the seeded rows are indistinguishable from recorded
 * drives. The Android peer of the iOS `/history?action=seed` debug endpoint.
 */
internal object HistorySeeder {

    /**
     * One scripted traversal. [deltaFromLimitKmh] is added to the zone's
     * vehicle-resolved limit to get the held average, so the over/under-limit mix
     * holds regardless of which real zone (and limit) the scenario lands on — a
     * negative delta stays green, a positive one flips the row red.
     */
    private data class Scenario(
        val vehicle: VehicleType,
        val dayOffset: Int,
        val hour: Int,
        val minute: Int,
        val deltaFromLimitKmh: Double,
        val durationSec: Int,
    )

    // Fixed script — deterministic so repeated seeds look identical. Covers all
    // four vehicle types, both sides of the limit, short/long traversals, and a
    // spread of days (today back to ~a month ago).
    private val scenarios = listOf(
        Scenario(VehicleType.CAR, 0, 8, 12, -22.0, 210),
        Scenario(VehicleType.CAR, 0, 17, 40, 9.0, 240),
        Scenario(VehicleType.TRUCK, 1, 10, 5, -12.0, 300),
        Scenario(VehicleType.CAR, 1, 19, 22, -2.0, 180),
        Scenario(VehicleType.BUS, 3, 7, 33, 6.0, 260),
        Scenario(VehicleType.MOTORCYCLE, 3, 14, 50, -8.0, 150),
        Scenario(VehicleType.CAR, 5, 9, 18, -44.0, 200),
        Scenario(VehicleType.TRUCK, 8, 12, 47, 5.0, 280),
        Scenario(VehicleType.CAR, 12, 16, 9, -16.0, 220),
        Scenario(VehicleType.BUS, 15, 11, 55, -8.0, 240),
        Scenario(VehicleType.CAR, 20, 18, 3, 3.0, 200),
        Scenario(VehicleType.MOTORCYCLE, 26, 13, 27, -12.0, 160),
    )

    /**
     * Wipe the History DB and refill it with [count] curated records. Returns the
     * number inserted. [count] above the script length cycles the scenarios,
     * pushing each extra pass ~a month further back so the day-grouped list keeps
     * gaining older sections. [zones] should be the app's loaded zones so records
     * reference real roads; falls back to a small built-in BG-highway set when
     * none are loaded yet.
     */
    suspend fun seed(
        historyRepository: HistoryRepository,
        gson: Gson,
        zones: List<Zone>,
        count: Int,
        nowMs: Long,
    ): Int {
        val pool = zones.ifEmpty { fallbackZones }
        historyRepository.clearAll()
        val total = max(1, count)
        var inserted = 0
        for (i in 0 until total) {
            val scenario = scenarios[i % scenarios.size]
            val cyclePush = (i / scenarios.size) * 30
            val zone = pool[i % pool.size]
            val limit = scenario.vehicle.limit(zone.speedLimits)
            val targetAvg = max(20.0, limit + scenario.deltaFromLimitKmh)

            val (entryMs, exitMs) = traversalBounds(
                nowMs = nowMs,
                dayOffset = scenario.dayOffset + cyclePush,
                hour = scenario.hour,
                minute = scenario.minute,
                durationSec = scenario.durationSec,
            )

            val samples = makeSamples(
                entryMs = entryMs,
                durationSec = ((exitMs - entryMs) / 1000).toInt(),
                targetAvgKmh = targetAvg,
                seed = i.toLong() * 2_654_435_761L,
            )
            val avg = HistoryStats.runningAverage(samples).lastOrNull()?.speedKmh ?: targetAvg
            val (sustainedMin, sustainedMax) = HistoryStats.sustainedExtremes(samples)
            val stored = HistoryStats.downsample(samples)

            val entity = ZoneTraversalEntity(
                id = "${zone.id}-$exitMs",
                zoneId = zone.id,
                road = zone.road,
                roadLatin = zone.roadLatin,
                direction = zone.direction,
                speedLimitKmh = limit,
                // `.setting` matches the iOS seeder's `scenario.vehicle.rawValue`.
                vehicleType = scenario.vehicle.setting,
                entryTimeMs = entryMs,
                exitTimeMs = exitMs,
                avgSpeedKmh = avg,
                sustainedMinKmh = sustainedMin,
                sustainedMaxKmh = sustainedMax,
                isOverLimit = avg > limit,
                distanceM = zone.distanceM,
                samplesJson = stored.toSamplesJson(gson),
            )
            historyRepository.record(entity)
            inserted++
        }
        return inserted
    }

    /**
     * Entry/exit epoch-ms for a traversal on the target local calendar day at the
     * target time, stepped back by whole calendar days until it is fully in the
     * past (matters for `dayOffset == 0` when "now" is earlier in the day than
     * the scripted hour).
     *
     * Shifting by **days** rather than clamping the offset to `now` is what keeps
     * the fill realistic: it preserves each scenario's scripted time-of-day, so a
     * morning and an evening run of the same road stay hours apart. The old clamp
     * slid every future-scripted traversal onto `now - 1 min`, which collapsed
     * them onto a single timestamp — seeding just after midnight then showed the
     * same road driven East and West at the very same minute.
     */
    private fun traversalBounds(
        nowMs: Long,
        dayOffset: Int,
        hour: Int,
        minute: Int,
        durationSec: Int,
    ): Pair<Long, Long> {
        val zone = ZoneId.systemDefault()
        var day = Instant.ofEpochMilli(nowMs).atZone(zone).toLocalDate().minusDays(dayOffset.toLong())
        while (true) {
            val entryMs = day.atStartOfDay(zone)
                .plusSeconds((hour * 3600 + minute * 60).toLong())
                .toInstant()
                .toEpochMilli()
            val exitMs = entryMs + durationSec * 1000L
            if (exitMs <= nowMs) return entryMs to exitMs
            day = day.minusDays(1)
        }
    }

    /**
     * A plausible speed-over-time series at 1 Hz: an entry acceleration ramp, a
     * gently undulating cruise with deterministic noise, and an exit deceleration
     * — then shifted so the mean lands exactly on [targetAvgKmh] (uniform 1 s
     * spacing makes the arithmetic mean track the time-weighted one, so the stored
     * running average comes out on the intended side of the limit).
     */
    private fun makeSamples(
        entryMs: Long,
        durationSec: Int,
        targetAvgKmh: Double,
        seed: Long,
    ): List<SpeedSample> {
        val rng = Lcg(seed)
        val n = max(8, durationSec)
        val entryRamp = max(1, min(15, n / 4))
        val exitRamp = max(1, min(10, n / 5))
        val raw = DoubleArray(n)
        for (i in 0 until n) {
            var v = targetAvgKmh
            if (i < entryRamp) {
                val f = i.toDouble() / entryRamp
                v -= (targetAvgKmh * 0.18) * (1 - f)
            }
            if (i >= n - exitRamp) {
                val f = (n - i).toDouble() / exitRamp
                v -= (targetAvgKmh * 0.12) * (1 - f)
            }
            v += sin(i / 18.0) * 3.5
            v += (rng.nextUnit() - 0.5) * 5.0
            raw[i] = max(5.0, v)
        }
        val mean = raw.sum() / n
        val offset = targetAvgKmh - mean
        return (0 until n).map { i ->
            SpeedSample(entryMs + i * 1000L, max(5.0, raw[i] + offset))
        }
    }

    // Representative BG average-speed zones for the case where the app hasn't
    // loaded zones.json yet. Records are denormalized, so only the id / road /
    // direction / limits / distance are used — geometry is placeholder.
    private val fallbackZones = listOf(
        demoZone("trakiya-a1-demo", "А1 Тракия", "A1 Trakiya", "EAST", 140, 100, 23_800),
        demoZone("hemus-a2-demo", "А2 Хемус", "A2 Hemus", "WEST", 140, 100, 18_400),
        demoZone("struma-a3-demo", "А3 Струма", "A3 Struma", "SOUTH", 140, 100, 12_600),
        demoZone("topli-dol-demo", "Тунел Топли дол", "Topli Dol Tunnel", "NORTH", 100, 80, 3_100),
        demoZone("cherni-vrah-demo", "бул. Черни връх", "Cherni Vrah Blvd", "SOUTH", 90, 70, 2_400),
    )

    private fun demoZone(
        id: String,
        road: String,
        roadLatin: String,
        direction: String,
        car: Int,
        truck: Int,
        distanceM: Int,
    ): Zone = Zone(
        id = id,
        road = road,
        roadLatin = roadLatin,
        direction = direction,
        description = road,
        start = ZoneEndpoint(lat = 42.7, lng = 25.3),
        end = ZoneEndpoint(lat = 42.7, lng = 25.5),
        distanceM = distanceM,
        speedLimits = SpeedLimits(car = car, truck = truck, bus = truck, motorcycle = null),
        centerline = listOf(listOf(25.3, 42.7), listOf(25.5, 42.7)),
        source = "debug-seed",
        lastVerified = "2026-01-01",
    )

    /**
     * Small deterministic PRNG so the seeded data reproduces exactly. Kotlin `Long`
     * arithmetic wraps on overflow (no exception), matching Swift's `&*` / `&+`.
     * Not for cryptography.
     */
    private class Lcg(seed: Long) {
        private var state: Long = seed xor 0x9E37_79B9_7F4A_7C15uL.toLong()

        private fun next(): Long {
            state = state * 6_364_136_223_846_793_005L + 1_442_695_040_888_963_407L
            return state
        }

        fun nextUnit(): Double = (next() ushr 11).toDouble() / (1L shl 53).toDouble()
    }
}
