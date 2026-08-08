// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.auto

import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import androidx.core.graphics.withSave
import com.demosten.srednabg.core.GpsPoint
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZONE_COLOR_GREEN
import com.demosten.srednabg.core.ZONE_COLOR_NEUTRAL
import com.demosten.srednabg.core.ZoneState
import com.demosten.srednabg.core.zoneStatusColor

class MapRenderer {

    private val projection = MercatorProjection()

    private val backgroundPaint = Paint().apply {
        color = 0xFF1A1C1E.toInt()
        style = Paint.Style.FILL
    }

    private val inactiveZonePaint = Paint().apply {
        color = 0xFF3A5A7C.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 3f
        isAntiAlias = true
        pathEffect = DashPathEffect(floatArrayOf(20f, 10f), 0f)
    }

    private val activeZonePaint = Paint().apply {
        style = Paint.Style.STROKE
        strokeWidth = 8f
        isAntiAlias = true
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val positionFillPaint = Paint().apply {
        color = 0xFF42A5F5.toInt()
        style = Paint.Style.FILL
        isAntiAlias = true
    }

    private val positionBorderPaint = Paint().apply {
        color = 0xFFFFFFFF.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 3f
        isAntiAlias = true
    }

    private val endpointPaint = Paint().apply {
        style = Paint.Style.FILL
        isAntiAlias = true
    }

    private val path = Path()

    fun draw(
        canvas: Canvas,
        zones: List<Zone>,
        activeZone: Zone?,
        position: GpsPoint?,
        zoneState: ZoneState,
        zoomOverride: Double? = null,
        headingUp: Boolean = false,
        bearing: Double = 0.0,
    ) {
        val width = canvas.width
        val height = canvas.height

        // Background fills the whole surface — never rotated.
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), backgroundPaint)

        val pos = position ?: return

        val zoom = zoomOverride ?: if (activeZone != null) {
            projection.computeZoomToFit(activeZone.centerline, width, height, 100)
        } else {
            12.0
        }

        val cx = width / 2f
        val cy = height / 2f

        // World-aligned elements (zones, endpoints) rotate with the map in heading-up mode.
        canvas.withSave {
            if (headingUp) {
                rotate(-bearing.toFloat(), cx, cy)
            }

            for (zone in zones) {
                if (zone == activeZone) continue
                drawPolyline(this, zone.centerline, pos.lat, pos.lng, zoom, width, height, inactiveZonePaint)
            }

            if (activeZone != null) {
                activeZonePaint.color = when (zoneState) {
                    is ZoneState.InZone -> zoneStatusColor(zoneState, pos.speed)
                    // Neutral, not green: the traffic light is a verdict on the
                    // driver, and an entry we never witnessed earns no verdict.
                    is ZoneState.Unmeasured -> ZONE_COLOR_NEUTRAL
                    else -> ZONE_COLOR_GREEN
                }
                drawPolyline(this, activeZone.centerline, pos.lat, pos.lng, zoom, width, height, activeZonePaint)

                endpointPaint.color = 0xFF66BB6A.toInt()
                drawEndpoint(this, activeZone.start.lat, activeZone.start.lng, pos.lat, pos.lng, zoom, width, height)

                endpointPaint.color = 0xFFEF5350.toInt()
                drawEndpoint(this, activeZone.end.lat, activeZone.end.lng, pos.lat, pos.lng, zoom, width, height)
            }
        }

        // Screen-aligned elements (user marker, arrow) render unrotated.
        canvas.drawCircle(cx, cy, 12f, positionBorderPaint)
        canvas.drawCircle(cx, cy, 10f, positionFillPaint)

        if (pos.speed > 5.0) {
            canvas.withSave {
                // In heading-up mode the map is rotated to match heading, so the arrow
                // points up on screen when drawn unrotated. In north-up mode we rotate
                // the arrow to show direction of travel relative to north.
                if (!headingUp) {
                    rotate(bearing.toFloat(), cx, cy)
                }
                path.reset()
                path.moveTo(cx, cy - 20f)
                path.lineTo(cx - 7f, cy - 8f)
                path.lineTo(cx + 7f, cy - 8f)
                path.close()
                drawPath(path, positionFillPaint)
            }
        }
    }

    private fun drawPolyline(
        canvas: Canvas,
        centerline: List<List<Double>>,
        centerLat: Double,
        centerLng: Double,
        zoom: Double,
        width: Int,
        height: Int,
        paint: Paint,
    ) {
        if (centerline.size < 2) return
        path.reset()
        val (firstX, firstY) = projection.latLngToPixel(
            centerline[0][0], centerline[0][1], centerLat, centerLng, zoom, width, height,
        )
        path.moveTo(firstX, firstY)
        for (i in 1 until centerline.size) {
            val (x, y) = projection.latLngToPixel(
                centerline[i][0], centerline[i][1], centerLat, centerLng, zoom, width, height,
            )
            path.lineTo(x, y)
        }
        canvas.drawPath(path, paint)
    }

    private fun drawEndpoint(
        canvas: Canvas,
        lat: Double,
        lng: Double,
        centerLat: Double,
        centerLng: Double,
        zoom: Double,
        width: Int,
        height: Int,
    ) {
        val (x, y) = projection.latLngToPixel(lat, lng, centerLat, centerLng, zoom, width, height)
        canvas.drawCircle(x, y, 8f, endpointPaint)
    }
}
