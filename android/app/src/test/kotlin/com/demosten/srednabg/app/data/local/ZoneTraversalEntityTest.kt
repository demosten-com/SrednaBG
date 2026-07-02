// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.local

import com.demosten.srednabg.core.SpeedSample
import com.google.gson.FieldNamingPolicy
import com.google.gson.GsonBuilder
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ZoneTraversalEntityTest {

    // Same Gson configuration AppModule.provideGson() builds, so the
    // serialize/parse pair matches what the app actually persists.
    private val gson = GsonBuilder()
        .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
        .create()

    @Test
    fun `samples round-trip through the JSON column`() {
        val samples = listOf(
            SpeedSample(1000, 88.5),
            SpeedSample(2000, 120.0),
            SpeedSample(3000, 133.3),
        )
        val json = samples.toSamplesJson(gson)
        val entity = entityWith(json)
        assertEquals(samples, entity.speedSamples(gson))
    }

    @Test
    fun `blank samples column parses to empty list`() {
        assertTrue(entityWith("").speedSamples(gson).isEmpty())
    }

    @Test
    fun `malformed samples column parses to empty list, not a crash`() {
        assertTrue(entityWith("{not valid json").speedSamples(gson).isEmpty())
    }

    private fun entityWith(samplesJson: String) = ZoneTraversalEntity(
        id = "id",
        zoneId = "zone",
        road = "road",
        roadLatin = null,
        direction = "east",
        speedLimitKmh = 140,
        vehicleType = "car",
        entryTimeMs = 0,
        exitTimeMs = 60_000,
        avgSpeedKmh = 120.0,
        sustainedMinKmh = 100.0,
        sustainedMaxKmh = 130.0,
        isOverLimit = false,
        distanceM = 19160,
        samplesJson = samplesJson,
    )
}
