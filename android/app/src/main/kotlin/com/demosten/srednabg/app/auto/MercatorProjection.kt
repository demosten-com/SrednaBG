// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.auto

import kotlin.math.PI
import kotlin.math.atan
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.tan

class MercatorProjection {

    private val TILE_SIZE = 256.0

    fun latLngToPixel(
        lat: Double,
        lng: Double,
        centerLat: Double,
        centerLng: Double,
        zoom: Double,
        screenWidth: Int,
        screenHeight: Int,
    ): Pair<Float, Float> {
        val scale = TILE_SIZE * 2.0.pow(zoom)

        val centerX = ((centerLng + 180.0) / 360.0) * scale
        val centerY = (1.0 - ln(tan(Math.toRadians(centerLat)) +
            1.0 / cos(Math.toRadians(centerLat))) / PI) / 2.0 * scale

        val targetX = ((lng + 180.0) / 360.0) * scale
        val targetY = (1.0 - ln(tan(Math.toRadians(lat)) +
            1.0 / cos(Math.toRadians(lat))) / PI) / 2.0 * scale

        val screenX = (targetX - centerX + screenWidth / 2.0).toFloat()
        val screenY = (targetY - centerY + screenHeight / 2.0).toFloat()

        return screenX to screenY
    }

    fun computeZoomToFit(
        points: List<List<Double>>,
        screenWidth: Int,
        screenHeight: Int,
        padding: Int = 80,
    ): Double {
        if (points.size < 2) return 14.0

        var minLat = Double.MAX_VALUE
        var maxLat = -Double.MAX_VALUE
        var minLng = Double.MAX_VALUE
        var maxLng = -Double.MAX_VALUE

        for (point in points) {
            if (point.size < 2) continue
            minLat = min(minLat, point[0])
            maxLat = max(maxLat, point[0])
            minLng = min(minLng, point[1])
            maxLng = max(maxLng, point[1])
        }

        val usableWidth = max(screenWidth - 2 * padding, 1)
        val usableHeight = max(screenHeight - 2 * padding, 1)

        val latSpan = maxLat - minLat
        val lngSpan = maxLng - minLng

        if (latSpan <= 0 && lngSpan <= 0) return 14.0

        val centerLat = (minLat + maxLat) / 2.0

        // Approximate meters per degree
        val metersPerDegLat = 111320.0
        val metersPerDegLng = 111320.0 * cos(Math.toRadians(centerLat))

        val spanMetersX = lngSpan * metersPerDegLng
        val spanMetersY = latSpan * metersPerDegLat

        // At zoom level z, meters per pixel ≈ 156543 * cos(lat) / 2^z
        val metersPerPixelX = if (usableWidth > 0 && spanMetersX > 0) spanMetersX / usableWidth else 0.1
        val metersPerPixelY = if (usableHeight > 0 && spanMetersY > 0) spanMetersY / usableHeight else 0.1
        val metersPerPixel = max(metersPerPixelX, metersPerPixelY)

        val baseMetersPerPixel = 156543.0 * cos(Math.toRadians(centerLat))
        val zoom = ln(baseMetersPerPixel / metersPerPixel) / ln(2.0)

        return zoom.coerceIn(5.0, 18.0)
    }
}
