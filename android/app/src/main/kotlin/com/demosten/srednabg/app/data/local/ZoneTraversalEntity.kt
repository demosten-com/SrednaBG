// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.demosten.srednabg.core.SpeedSample
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

/**
 * A completed average-speed-zone traversal, persisted for the History tab.
 *
 * Fields are **denormalized** on purpose: the zone's road/direction/limit and
 * the driver's speeds are all copied in, so a record survives the source zone
 * being edited, re-numbered, or deleted by a later data sync. The captured
 * speed-over-time series lives in [samplesJson] as a JSON array (mirroring
 * [ZoneEntity.centerlineJson]), downsampled to ≤500 points before storage.
 */
@Entity(tableName = "zone_traversals")
data class ZoneTraversalEntity(
    @PrimaryKey val id: String,
    val zoneId: String,
    val road: String,
    val roadLatin: String?,
    val direction: String,
    val speedLimitKmh: Int,
    val vehicleType: String,
    val entryTimeMs: Long,
    val exitTimeMs: Long,
    val avgSpeedKmh: Double?,
    val sustainedMinKmh: Double,
    val sustainedMaxKmh: Double,
    val isOverLimit: Boolean,
    val distanceM: Int,
    val samplesJson: String,
)

private val speedSampleListType = object : TypeToken<List<SpeedSample>>() {}.type

/**
 * Serialize a captured series to the JSON array stored in [ZoneTraversalEntity.samplesJson].
 *
 * Casing note: the injected [Gson] is the shared app singleton configured with
 * `FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES` (see `AppModule.provideGson`),
 * so keys serialize as `timestamp_ms` / `speed_kmh` (**snake_case**). The iOS
 * port encodes the same [SpeedSample] with `JSONEncoder` defaults
 * (`timestampMs` / `speedKmh`, **camelCase**). Each platform round-trips its own
 * blob, so this is not a runtime bug — but a future cross-platform history
 * import/export must reconcile the casing (the shared `Gson` can't simply be
 * re-cased here without also changing zone-API parsing). Kept intentionally.
 */
fun List<SpeedSample>.toSamplesJson(gson: Gson): String = gson.toJson(this, speedSampleListType)

/** Parse [ZoneTraversalEntity.samplesJson] back into a [SpeedSample] series (empty on malformed/blank). */
fun ZoneTraversalEntity.speedSamples(gson: Gson): List<SpeedSample> {
    if (samplesJson.isBlank()) return emptyList()
    return runCatching { gson.fromJson<List<SpeedSample>>(samplesJson, speedSampleListType) }
        .getOrNull()
        ?: emptyList()
}
