// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.ValueSource

/**
 * Guards against the class of bug where GPX files produced by
 * scrapers/scripts/make_test_route.py drift off-road on the approach, causing
 * ZoneDetector to miss zone entry until the drive is already deep inside the
 * zone. Regenerate fixtures via:
 *
 *   cd scrapers && python -m src.output   # enriches zones.json
 *   python scripts/make_test_route.py --zone-id <id> \
 *       --out ../android/core/src/test/resources/gpx/<id>.gpx
 *   # then copy the enriched zone entry into zones_subset.json
 */
class GeneratedGpxDetectionTest {

    @ParameterizedTest
    @ValueSource(strings = ["struma-02-south"])
    fun `generated GPX enters zone before midpoint and exits cleanly`(zoneId: String) {
        val zone = loadZone(zoneId)
        val gpxPoints = parseGpx("/gpx/$zoneId.gpx")
        require(gpxPoints.size > 20) { "GPX fixture suspiciously short: ${gpxPoints.size}" }

        // The zone boundary must be an explicit point in the GPX. Without this
        // guarantee the original bug could recur: whole-polyline resampling at
        // step_m can skip past the centerline[0] vertex, landing the zone
        // crossing "between samples" and shifting detected entry by up to a
        // full sample interval.
        val c0 = zone.centerline.first()
        val zoneStartIdx = gpxPoints.indexOfFirst { it.lat == c0[0] && it.lng == c0[1] }
        assertTrue(
            zoneStartIdx >= 0,
            "Zone $zoneId centerline[0] (${c0[0]}, ${c0[1]}) is not an explicit GPX " +
                "point — make_test_route.py must emit the zone boundary verbatim",
        )

        val detector = ZoneDetector(listOf(zone))
        val states = gpxPoints.map { detector.update(it) }

        val firstInZoneIdx = states.indexOfFirst { it is ZoneState.InZone }
        assertTrue(firstInZoneIdx >= 0, "Zone $zoneId was never entered during playback")

        // Entry must fire no later than the GPX point at centerline[0] — in
        // practice slightly earlier, because ZoneDetector.ENTRY_DISTANCE_M is
        // 500m. A non-trivially-later entry would mean the detector missed the
        // transition even with the zone start explicitly present.
        assertTrue(
            firstInZoneIdx <= zoneStartIdx,
            "Zone $zoneId entry fired at GPX index $firstInZoneIdx, AFTER " +
                "the explicit zone-start sample at $zoneStartIdx — detector lost the transition",
        )

        assertTrue(
            states.any { it is ZoneState.Exiting },
            "Zone $zoneId never exited — centerline traversal did not complete",
        )

        val inZoneCount = states.count { it is ZoneState.InZone }
        assertTrue(
            inZoneCount >= gpxPoints.size * 0.25,
            "Only $inZoneCount / ${gpxPoints.size} points registered InZone — " +
                "detector is losing the zone mid-traversal",
        )
    }

    private fun loadZone(zoneId: String): Zone {
        val stream = javaClass.getResourceAsStream("/zones_subset.json")
            ?: error("Missing test resource /zones_subset.json")
        val body = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        val json = Json { ignoreUnknownKeys = true }
        val db = json.decodeFromString(TestZoneDatabase.serializer(), body)
        return db.zones.firstOrNull { it.id == zoneId }?.toCoreZone()
            ?: error("Zone $zoneId missing from zones_subset.json")
    }

    private fun parseGpx(resourcePath: String): List<GpsPoint> {
        val stream = javaClass.getResourceAsStream(resourcePath)
            ?: error("Missing GPX fixture $resourcePath")
        val xml = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        val trkptRe = Regex("""<trkpt\s+lat="([\d.\-]+)"\s+lon="([\d.\-]+)">""")
        val coords: List<Pair<Double, Double>> = trkptRe.findAll(xml)
            .map { it.groupValues[1].toDouble() to it.groupValues[2].toDouble() }
            .toList()
        require(coords.size >= 2) { "Not enough trkpt entries in $resourcePath" }

        // Generate a synthetic 1 Hz timeline. Playback speed doesn't affect detection
        // so long as we stay above ZoneDetector.STOP_SPEED_KMH everywhere.
        val dtMs = 1_000L
        val epochBase = 1_700_000_000_000L
        val points = ArrayList<GpsPoint>(coords.size)
        for (i in coords.indices) {
            val (lat, lng) = coords[i]
            val bearing = if (i == 0) {
                bearingBetween(coords[0].first, coords[0].second, coords[1].first, coords[1].second)
            } else {
                bearingBetween(coords[i - 1].first, coords[i - 1].second, lat, lng)
            }
            // Speed estimated from haversine; first point inherits from second.
            val speedKmh = if (i == 0) {
                haversineDistance(
                    coords[0].first, coords[0].second, coords[1].first, coords[1].second,
                ) * 3.6
            } else {
                haversineDistance(
                    coords[i - 1].first, coords[i - 1].second, lat, lng,
                ) * 3.6
            }
            points += GpsPoint(
                lat = lat,
                lng = lng,
                speed = speedKmh,
                timestamp = epochBase + i * dtMs,
                bearing = bearing,
            )
        }
        return points
    }
}

@Serializable
private data class TestZoneDatabase(val zones: List<TestZoneDto>)

@Serializable
private data class TestZoneDto(
    val id: String,
    val road: String,
    @SerialName("road_latin") val roadLatin: String? = null,
    val direction: String,
    val description: String,
    val start: TestEndpointDto,
    val end: TestEndpointDto,
    @SerialName("distance_m") val distanceM: Int,
    @SerialName("speed_limits") val speedLimits: TestSpeedLimitsDto,
    val centerline: List<List<Double>>,
    val source: String,
    @SerialName("last_verified") val lastVerified: String,
) {
    fun toCoreZone() = Zone(
        id = id,
        road = road,
        roadLatin = roadLatin,
        direction = direction,
        description = description,
        start = start.toCore(),
        end = end.toCore(),
        distanceM = distanceM,
        speedLimits = speedLimits.toCore(),
        centerline = centerline,
        source = source,
        lastVerified = lastVerified,
    )
}

@Serializable
private data class TestEndpointDto(
    val lat: Double,
    val lng: Double,
    @SerialName("km_marker") val kmMarker: String? = null,
    val settlement: String? = null,
    @SerialName("settlement_latin") val settlementLatin: String? = null,
) {
    fun toCore() = ZoneEndpoint(lat, lng, kmMarker, settlement, settlementLatin)
}

@Serializable
private data class TestSpeedLimitsDto(
    val car: Int,
    val truck: Int,
    val bus: Int,
    val motorcycle: Int? = null,
) {
    fun toCore() = SpeedLimits(car, truck, bus, motorcycle)
}
