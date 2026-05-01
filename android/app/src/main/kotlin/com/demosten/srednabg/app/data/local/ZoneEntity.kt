// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.demosten.srednabg.core.SpeedLimits
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneEndpoint
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

@Entity(tableName = "zones")
data class ZoneEntity(
    @PrimaryKey val id: String,
    val road: String,
    val roadLatin: String?,
    val direction: String,
    val description: String,
    val startLat: Double,
    val startLng: Double,
    val startKmMarker: String?,
    val startSettlement: String?,
    val startSettlementLatin: String?,
    val endLat: Double,
    val endLng: Double,
    val endKmMarker: String?,
    val endSettlement: String?,
    val endSettlementLatin: String?,
    val distanceM: Int,
    val speedLimitCar: Int,
    val speedLimitTruck: Int,
    val speedLimitBus: Int,
    val speedLimitMotorcycle: Int?,
    val centerlineJson: String,
    val source: String,
    val lastVerified: String,
)

fun ZoneEntity.toCoreZone(gson: Gson): Zone {
    val centerlineType = object : TypeToken<List<List<Double>>>() {}.type
    val centerline: List<List<Double>> = gson.fromJson(centerlineJson, centerlineType)
    return Zone(
        id = id,
        road = road,
        roadLatin = roadLatin,
        direction = direction,
        description = description,
        start = ZoneEndpoint(
            lat = startLat,
            lng = startLng,
            kmMarker = startKmMarker,
            settlement = startSettlement,
            settlementLatin = startSettlementLatin,
        ),
        end = ZoneEndpoint(
            lat = endLat,
            lng = endLng,
            kmMarker = endKmMarker,
            settlement = endSettlement,
            settlementLatin = endSettlementLatin,
        ),
        distanceM = distanceM,
        speedLimits = SpeedLimits(
            car = speedLimitCar,
            truck = speedLimitTruck,
            bus = speedLimitBus,
            motorcycle = speedLimitMotorcycle,
        ),
        centerline = centerline,
        source = source,
        lastVerified = lastVerified,
    )
}

fun Zone.toEntity(gson: Gson): ZoneEntity {
    return ZoneEntity(
        id = id,
        road = road,
        roadLatin = roadLatin,
        direction = direction,
        description = description,
        startLat = start.lat,
        startLng = start.lng,
        startKmMarker = start.kmMarker,
        startSettlement = start.settlement,
        startSettlementLatin = start.settlementLatin,
        endLat = end.lat,
        endLng = end.lng,
        endKmMarker = end.kmMarker,
        endSettlement = end.settlement,
        endSettlementLatin = end.settlementLatin,
        distanceM = distanceM,
        speedLimitCar = speedLimits.car,
        speedLimitTruck = speedLimits.truck,
        speedLimitBus = speedLimits.bus,
        speedLimitMotorcycle = speedLimits.motorcycle,
        centerlineJson = gson.toJson(centerline),
        source = source,
        lastVerified = lastVerified,
    )
}
