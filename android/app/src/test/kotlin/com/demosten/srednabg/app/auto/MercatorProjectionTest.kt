// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.auto

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

class MercatorProjectionTest {

    private lateinit var projection: MercatorProjection

    @BeforeEach
    fun setUp() {
        projection = MercatorProjection()
    }

    @Test
    fun `latLngToPixel center point returns screen center`() {
        val (x, y) = projection.latLngToPixel(
            lat = 42.7,
            lng = 23.3,
            centerLat = 42.7,
            centerLng = 23.3,
            zoom = 10.0,
            screenWidth = 800,
            screenHeight = 600,
        )

        assertEquals(400f, x, 0.5f)
        assertEquals(300f, y, 0.5f)
    }

    @Test
    fun `latLngToPixel offset point is displaced from center`() {
        val (centerX, centerY) = projection.latLngToPixel(
            lat = 42.7, lng = 23.3,
            centerLat = 42.7, centerLng = 23.3,
            zoom = 10.0, screenWidth = 800, screenHeight = 600,
        )
        val (offsetX, offsetY) = projection.latLngToPixel(
            lat = 42.71, lng = 23.31,
            centerLat = 42.7, centerLng = 23.3,
            zoom = 10.0, screenWidth = 800, screenHeight = 600,
        )

        // Point to the east should have larger X
        assertTrue(offsetX > centerX, "East point should have larger X")
        // Point to the north should have smaller Y (screen coords)
        assertTrue(offsetY < centerY, "North point should have smaller Y")
    }

    @Test
    fun `computeZoomToFit returns reasonable zoom for Bulgaria-scale points`() {
        // Bulgaria roughly spans 42-44 lat, 22-29 lng
        val bulgariaCorners = listOf(
            listOf(42.0, 22.0),
            listOf(44.0, 29.0),
        )

        val zoom = projection.computeZoomToFit(
            points = bulgariaCorners,
            screenWidth = 800,
            screenHeight = 600,
        )

        assertTrue(zoom in 5.0..10.0, "Bulgaria should fit at zoom 5-10, got $zoom")
    }

    @Test
    fun `computeZoomToFit single point returns default zoom`() {
        val zoom = projection.computeZoomToFit(
            points = listOf(listOf(42.7, 23.3)),
            screenWidth = 800,
            screenHeight = 600,
        )

        assertEquals(14.0, zoom)
    }

    @Test
    fun `computeZoomToFit clamps between 5 and 18`() {
        // Two very close points should try to zoom in a lot, but clamp at 18
        val closePoints = listOf(
            listOf(42.700000, 23.300000),
            listOf(42.700001, 23.300001),
        )
        val zoomClose = projection.computeZoomToFit(closePoints, 800, 600)
        assertTrue(zoomClose <= 18.0, "Zoom should be clamped at 18, got $zoomClose")

        // Two very far points should try to zoom out a lot, but clamp at 5
        val farPoints = listOf(
            listOf(-60.0, -170.0),
            listOf(60.0, 170.0),
        )
        val zoomFar = projection.computeZoomToFit(farPoints, 800, 600)
        assertTrue(zoomFar >= 5.0, "Zoom should be clamped at 5, got $zoomFar")
    }

    @Test
    fun `computeZoomToFit respects screen dimensions`() {
        val points = listOf(
            listOf(42.0, 23.0),
            listOf(42.5, 23.5),
        )

        val zoomWide = projection.computeZoomToFit(points, 1600, 600)
        val zoomTall = projection.computeZoomToFit(points, 600, 1600)

        // Different aspect ratios should produce different zooms
        // A wider screen can fit the same area at a higher zoom
        assertTrue(zoomWide != zoomTall, "Different aspect ratios should produce different zooms")
    }
}
