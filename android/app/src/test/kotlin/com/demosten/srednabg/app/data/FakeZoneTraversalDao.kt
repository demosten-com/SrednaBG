// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import com.demosten.srednabg.app.data.local.ZoneTraversalDao
import com.demosten.srednabg.app.data.local.ZoneTraversalEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map

/**
 * In-memory [ZoneTraversalDao] for JVM unit tests — the app module has no
 * Robolectric / instrumented-DB harness, so history persistence is exercised
 * against this fake (Room's own SQL is validated at runtime by the app / QA).
 */
class FakeZoneTraversalDao : ZoneTraversalDao {
    private val rows = MutableStateFlow<List<ZoneTraversalEntity>>(emptyList())

    override suspend fun insert(traversal: ZoneTraversalEntity) {
        rows.value = rows.value.filterNot { it.id == traversal.id } + traversal
    }

    override fun getAll(): Flow<List<ZoneTraversalEntity>> =
        rows.map { list -> list.sortedByDescending { it.exitTimeMs } }

    override suspend fun getById(id: String): ZoneTraversalEntity? =
        rows.value.firstOrNull { it.id == id }

    override suspend fun latest(): ZoneTraversalEntity? =
        rows.value.maxByOrNull { it.exitTimeMs }

    override suspend fun deleteOlderThan(cutoffMs: Long) {
        rows.value = rows.value.filter { it.exitTimeMs >= cutoffMs }
    }

    override suspend fun deleteAll() {
        rows.value = emptyList()
    }

    override suspend fun count(): Int = rows.value.size
}

fun traversalEntity(
    id: String,
    exitTimeMs: Long,
    entryTimeMs: Long = exitTimeMs - 60_000,
    avgSpeedKmh: Double? = 120.0,
    isOverLimit: Boolean = false,
    road: String = "АМ Тракия",
    roadLatin: String? = "Trakiya",
) = ZoneTraversalEntity(
    id = id,
    zoneId = "zone-$id",
    road = road,
    roadLatin = roadLatin,
    direction = "east",
    speedLimitKmh = 140,
    vehicleType = "car",
    entryTimeMs = entryTimeMs,
    exitTimeMs = exitTimeMs,
    avgSpeedKmh = avgSpeedKmh,
    sustainedMinKmh = 100.0,
    sustainedMaxKmh = 130.0,
    isOverLimit = isOverLimit,
    distanceM = 19160,
    samplesJson = "[]",
)
