// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.auto

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import com.demosten.srednabg.app.ui.util.orDash
import com.demosten.srednabg.core.ZoneState
import kotlin.math.max
import kotlin.math.min

data class OverlayLabels(
    val overLimit: String,
    val withinLimit: String,
    val monitoringHint: String,
    /** Short form for a zone we're in but didn't see entered — must clear the glyph floors. */
    val unmeasuredHint: String,
    val nowSpeedFormat: String,
    val kmhLabel: String,
    val zoneComplete: String,
    val maxForRemainderFormat: String,
)

private const val HERO_MIN_PX = 64f
private const val PRIMARY_MIN_PX = 28f
private const val SECONDARY_MIN_PX = 24f
private const val BADGE_MIN_PX = 40f

private fun textPx(panelHeight: Float, ratio: Float, minPx: Float): Float =
    max(panelHeight * ratio, minPx)

class SpeedOverlay {

    private val panelPaint = Paint().apply {
        color = 0xB3000000.toInt() // black 70% opacity
        style = Paint.Style.FILL
        isAntiAlias = true
    }

    private val speedTextPaint = Paint().apply {
        style = Paint.Style.FILL
        isAntiAlias = true
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
    }

    private val labelTextPaint = Paint().apply {
        color = 0xCCFFFFFF.toInt() // white 80% opacity
        style = Paint.Style.FILL
        isAntiAlias = true
        textAlign = Paint.Align.CENTER
    }

    private val statusTextPaint = Paint().apply {
        style = Paint.Style.FILL
        isAntiAlias = true
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
    }

    private val limitCirclePaint = Paint().apply {
        color = 0xFFFFFFFF.toInt()
        style = Paint.Style.FILL
        isAntiAlias = true
    }

    private val limitBorderPaint = Paint().apply {
        color = 0xFFEF5350.toInt()
        style = Paint.Style.STROKE
        isAntiAlias = true
    }

    private val limitTextPaint = Paint().apply {
        color = 0xFF000000.toInt()
        style = Paint.Style.FILL
        isAntiAlias = true
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
    }

    private val progressBgPaint = Paint().apply {
        color = 0x33FFFFFF.toInt() // white 20% opacity
        style = Paint.Style.FILL
    }

    private val progressFillPaint = Paint().apply {
        style = Paint.Style.FILL
    }

    fun draw(
        canvas: Canvas,
        stableArea: Rect,
        zoneState: ZoneState,
        speedLimit: Int,
        currentSpeedKmh: Double?,
        labels: OverlayLabels,
    ) {
        when (zoneState) {
            is ZoneState.Outside -> drawOutside(canvas, stableArea, currentSpeedKmh, labels)
            // Same compact two-row panel as Outside — live speed plus a hint —
            // because there is no average, no remainder and no verdict to draw.
            // The only change is what the hint says.
            is ZoneState.Unmeasured ->
                drawOutside(canvas, stableArea, currentSpeedKmh, labels, hint = labels.unmeasuredHint)
            is ZoneState.InZone -> drawInZone(canvas, stableArea, zoneState, speedLimit, currentSpeedKmh, labels)
            is ZoneState.Exiting ->
                drawExiting(canvas, stableArea, zoneState, speedLimit, currentSpeedKmh, labels)
        }
    }

    private fun drawOutside(
        canvas: Canvas,
        area: Rect,
        currentSpeedKmh: Double?,
        labels: OverlayLabels,
        hint: String = labels.monitoringHint,
    ) {
        // Two rows: "VALUE km/h" sharing a baseline, then "Monitoring zones".
        // Text sizes scale with stable area; floors keep glyphs readable on a
        // small projection surface; panel grows to fit — never the other way.
        speedTextPaint.textSize = max(area.height() * 0.18f, HERO_MIN_PX)
        speedTextPaint.color = 0xFFFFFFFF.toInt()
        labelTextPaint.textSize = max(area.height() * 0.07f, PRIMARY_MIN_PX)

        val heroFm = speedTextPaint.fontMetrics
        val labelFm = labelTextPaint.fontMetrics
        val heroLine = -heroFm.ascent + heroFm.descent
        val labelLine = -labelFm.ascent + labelFm.descent

        val topPad = 16f
        val botPad = 16f
        val gap = 8f
        val panelHeight = topPad + heroLine + gap + labelLine + botPad

        val valueStr = currentSpeedKmh.orDash()
        val unitStr = " " + labels.kmhLabel

        val savedSpeedAlign = speedTextPaint.textAlign
        val savedLabelAlign = labelTextPaint.textAlign
        speedTextPaint.textAlign = Paint.Align.LEFT
        labelTextPaint.textAlign = Paint.Align.LEFT
        val valueWidth = speedTextPaint.measureText(valueStr)
        val unitWidth = labelTextPaint.measureText(unitStr)
        val topLineWidth = valueWidth + unitWidth

        labelTextPaint.textAlign = Paint.Align.CENTER
        val hintWidth = labelTextPaint.measureText(hint)
        val panelWidth = max(max(topLineWidth, hintWidth) + 56f, area.width() * 0.28f)
            .coerceAtMost(area.width() * 0.6f)

        val panelLeft = area.centerX() - panelWidth / 2f
        val panelTop = area.bottom - panelHeight - 16f
        val panelRect = RectF(panelLeft, panelTop, panelLeft + panelWidth, panelTop + panelHeight)
        canvas.drawRoundRect(panelRect, 16f, 16f, panelPaint)

        val cx = panelRect.centerX()
        // Row 1: baseline-aligned "VALUE km/h" centred horizontally.
        val row1Baseline = panelTop + topPad - heroFm.ascent
        val row1Start = cx - topLineWidth / 2f
        speedTextPaint.textAlign = Paint.Align.LEFT
        labelTextPaint.textAlign = Paint.Align.LEFT
        canvas.drawText(valueStr, row1Start, row1Baseline, speedTextPaint)
        labelTextPaint.textSize = max(area.height() * 0.07f, PRIMARY_MIN_PX)
        canvas.drawText(unitStr, row1Start + valueWidth, row1Baseline, labelTextPaint)

        // Row 2: the hint ("Monitoring zones" / "Not measured") centred.
        labelTextPaint.textAlign = Paint.Align.CENTER
        val row2Baseline = row1Baseline + heroFm.descent + gap - labelFm.ascent
        canvas.drawText(hint, cx, row2Baseline, labelTextPaint)

        speedTextPaint.textAlign = savedSpeedAlign
        labelTextPaint.textAlign = savedLabelAlign
    }

    private fun drawInZone(
        canvas: Canvas,
        area: Rect,
        state: ZoneState.InZone,
        speedLimit: Int,
        currentSpeedKmh: Double?,
        labels: OverlayLabels,
    ) {
        val statusColor = getStatusColor(state, speedLimit, currentSpeedKmh)

        // Compact 2-row layout so the panel doesn't reach the centre of the
        // canvas (where the user dot lives). Hero + unit share a baseline;
        // status/over-limit is communicated by colour (hero + progress + max
        // all turn red when over) rather than a dedicated text row.
        val heroSize = max(area.height() * 0.14f, HERO_MIN_PX)
        val primarySize = max(area.height() * 0.055f, PRIMARY_MIN_PX)
        val secondarySize = max(area.height() * 0.045f, SECONDARY_MIN_PX)

        speedTextPaint.textSize = heroSize
        speedTextPaint.color = statusColor
        labelTextPaint.textSize = primarySize
        val heroFm = speedTextPaint.fontMetrics
        val primaryFm = labelTextPaint.fontMetrics
        val heroLine = -heroFm.ascent + heroFm.descent
        val primaryLine = -primaryFm.ascent + primaryFm.descent
        labelTextPaint.textSize = secondarySize
        val secondaryFm = labelTextPaint.fontMetrics
        val secondaryLine = -secondaryFm.ascent + secondaryFm.descent

        val gap = 6f
        val topPad = 12f
        val botPad = 12f
        val progressHeight = max(area.height() * 0.01f, 5f)
        // Left: [hero km/h] + "Now XXX km/h"
        val leftContent = heroLine + gap + secondaryLine
        // Right: "X.X km" + progress + "Max X km/h"
        val rightContent = primaryLine + gap + progressHeight + gap + primaryLine
        val contentHeight = max(leftContent, rightContent)
        val panelHeight = topPad + contentHeight + botPad

        val panelWidth = (area.width() * 0.85f).coerceAtMost(880f)
        val panelLeft = area.centerX() - panelWidth / 2f
        val panelTop = area.bottom - panelHeight - 16f
        val panelRect = RectF(panelLeft, panelTop, panelLeft + panelWidth, panelTop + panelHeight)
        canvas.drawRoundRect(panelRect, 16f, 16f, panelPaint)

        // Horizontal breathing room so text doesn't kiss the panel border.
        val hPad = 20f
        val innerWidth = panelWidth - 2f * hPad
        val colThird = innerWidth / 3f
        val avgSpeedCX = panelLeft + hPad + colThird / 2f
        val limitCenterX = panelLeft + panelWidth / 2f
        val rightX = panelLeft + panelWidth - hPad - colThird / 2f

        // --- LEFT COLUMN ---
        // Row 1: "[hero] km/h" sharing a baseline. Centre the composite
        // visually in the left column.
        val savedSpeedAlign = speedTextPaint.textAlign
        val savedLabelAlign = labelTextPaint.textAlign
        speedTextPaint.textSize = heroSize
        speedTextPaint.textAlign = Paint.Align.LEFT
        labelTextPaint.textSize = primarySize
        labelTextPaint.textAlign = Paint.Align.LEFT
        val valueStr = state.avgSpeed.orDash()
        val unitStr = " " + labels.kmhLabel
        val valueWidth = speedTextPaint.measureText(valueStr)
        val unitWidth = labelTextPaint.measureText(unitStr)
        val row1Width = valueWidth + unitWidth
        val row1Baseline = panelTop + topPad - heroFm.ascent
        val row1Start = avgSpeedCX - row1Width / 2f
        canvas.drawText(valueStr, row1Start, row1Baseline, speedTextPaint)
        canvas.drawText(unitStr, row1Start + valueWidth, row1Baseline, labelTextPaint)

        // Row 2: "Now XXX km/h" centred
        labelTextPaint.textSize = secondarySize
        labelTextPaint.textAlign = Paint.Align.CENTER
        val row2Baseline = row1Baseline + heroFm.descent + gap - secondaryFm.ascent
        canvas.drawText(
            labels.nowSpeedFormat.format(currentSpeedKmh.orDash()),
            avgSpeedCX,
            row2Baseline,
            labelTextPaint,
        )
        speedTextPaint.textAlign = savedSpeedAlign
        labelTextPaint.textAlign = savedLabelAlign

        // --- CENTER COLUMN (speed-limit badge, vertically centred) ---
        val limitCenterY = panelTop + panelHeight / 2f
        val limitRadius = min(panelHeight * 0.36f, colThird * 0.38f)
        limitBorderPaint.strokeWidth = max(limitRadius * 0.22f, 4f)
        canvas.drawCircle(limitCenterX, limitCenterY, limitRadius, limitCirclePaint)
        canvas.drawCircle(limitCenterX, limitCenterY, limitRadius, limitBorderPaint)
        // Inner usable width is the diameter minus the border stroke; pad a
        // bit so 3-digit numbers (e.g. 140) don't kiss the red ring.
        val limitLabel = "$speedLimit"
        val badgeInnerWidth = (limitRadius - limitBorderPaint.strokeWidth) * 2f * 0.8f
        limitTextPaint.textSize = limitRadius * 1.1f
        val rawWidth = limitTextPaint.measureText(limitLabel)
        if (rawWidth > badgeInnerWidth) {
            limitTextPaint.textSize *= badgeInnerWidth / rawWidth
        }
        val limitFm = limitTextPaint.fontMetrics
        canvas.drawText(
            limitLabel,
            limitCenterX,
            limitCenterY - (limitFm.ascent + limitFm.descent) / 2f,
            limitTextPaint,
        )

        // --- RIGHT COLUMN ---
        labelTextPaint.textSize = primarySize
        val distKm = state.distanceRemaining / 1000.0
        var rightBaseline = panelTop + topPad - primaryFm.ascent
        canvas.drawText("%.1f km".format(distKm), rightX, rightBaseline, labelTextPaint)

        val progressTop = rightBaseline + primaryFm.descent + gap
        val progressWidth = colThird * 0.75f
        val progressLeft = rightX - progressWidth / 2f
        val progressRect = RectF(progressLeft, progressTop, progressLeft + progressWidth, progressTop + progressHeight)
        canvas.drawRoundRect(progressRect, 3f, 3f, progressBgPaint)
        val totalDist = state.zone.distanceM.toDouble()
        val fraction = if (totalDist > 0) ((totalDist - state.distanceRemaining) / totalDist).coerceIn(0.0, 1.0) else 0.0
        progressFillPaint.color = statusColor
        val fillRect = RectF(progressLeft, progressTop, progressLeft + progressWidth * fraction.toFloat(), progressTop + progressHeight)
        canvas.drawRoundRect(fillRect, 3f, 3f, progressFillPaint)

        // "Max X km/h" — colour-coded to encode the over-limit status.
        labelTextPaint.textSize = primarySize
        labelTextPaint.color = statusColor
        rightBaseline = progressTop + progressHeight + gap - primaryFm.ascent
        canvas.drawText(
            labels.maxForRemainderFormat.format(state.speedStatus.maxSpeedForRemainder.toInt()),
            rightX,
            rightBaseline,
            labelTextPaint,
        )
        labelTextPaint.color = 0xCCFFFFFF.toInt() // restore default white
    }

    private fun drawExiting(
        canvas: Canvas,
        area: Rect,
        state: ZoneState.Exiting,
        speedLimit: Int,
        currentSpeedKmh: Double?,
        labels: OverlayLabels,
    ) {
        // Same vehicle-resolved limit the engine judged against in-zone — the
        // exit verdict must not flip back to the car limit.
        val finalAvg = state.finalAvgSpeed
        val color = if (finalAvg != null && finalAvg > speedLimit) 0xFFEF5350.toInt() else 0xFF66BB6A.toInt()

        // Metrics-based stacking so the header, hero, and "Now" line can't
        // overlap on small projection surfaces.
        val heroSize = max(area.height() * 0.14f, HERO_MIN_PX)
        val primarySize = max(area.height() * 0.055f, PRIMARY_MIN_PX)
        val secondarySize = max(area.height() * 0.045f, SECONDARY_MIN_PX)

        speedTextPaint.textSize = heroSize
        speedTextPaint.color = color
        labelTextPaint.textSize = primarySize
        val heroFm = speedTextPaint.fontMetrics
        val primaryFm = labelTextPaint.fontMetrics
        val heroLine = -heroFm.ascent + heroFm.descent
        val primaryLine = -primaryFm.ascent + primaryFm.descent
        labelTextPaint.textSize = secondarySize
        val secondaryFm = labelTextPaint.fontMetrics
        val secondaryLine = -secondaryFm.ascent + secondaryFm.descent

        val topPad = 12f
        val botPad = 12f
        val gap = 6f
        val contentHeight = primaryLine + gap + heroLine + gap + secondaryLine
        val panelHeight = topPad + contentHeight + botPad

        val savedSpeedAlign = speedTextPaint.textAlign
        val savedLabelAlign = labelTextPaint.textAlign
        speedTextPaint.textAlign = Paint.Align.LEFT
        labelTextPaint.textAlign = Paint.Align.LEFT
        speedTextPaint.textSize = heroSize
        labelTextPaint.textSize = primarySize
        val valueStr = state.finalAvgSpeed.orDash()
        val unitStr = " " + labels.kmhLabel
        val valueWidth = speedTextPaint.measureText(valueStr)
        val unitWidth = labelTextPaint.measureText(unitStr)
        val heroRowWidth = valueWidth + unitWidth

        labelTextPaint.textAlign = Paint.Align.CENTER
        labelTextPaint.textSize = primarySize
        val headerWidth = labelTextPaint.measureText(labels.zoneComplete)
        labelTextPaint.textSize = secondarySize
        val nowWidth = labelTextPaint.measureText(
            labels.nowSpeedFormat.format(currentSpeedKmh.orDash()),
        )

        val panelWidth = max(maxOf(heroRowWidth, headerWidth, nowWidth) + 56f, area.width() * 0.3f)
            .coerceAtMost(area.width() * 0.7f)

        val panelLeft = area.centerX() - panelWidth / 2f
        val panelTop = area.bottom - panelHeight - 16f
        val panelRect = RectF(panelLeft, panelTop, panelLeft + panelWidth, panelTop + panelHeight)
        canvas.drawRoundRect(panelRect, 16f, 16f, panelPaint)

        val cx = panelRect.centerX()

        // Row 1: "Zone complete"
        labelTextPaint.textSize = primarySize
        labelTextPaint.textAlign = Paint.Align.CENTER
        var baseline = panelTop + topPad - primaryFm.ascent
        canvas.drawText(labels.zoneComplete, cx, baseline, labelTextPaint)

        // Row 2: final avg + " km/h" baseline-aligned
        baseline += primaryFm.descent + gap - heroFm.ascent
        val heroStart = cx - heroRowWidth / 2f
        speedTextPaint.textAlign = Paint.Align.LEFT
        labelTextPaint.textAlign = Paint.Align.LEFT
        speedTextPaint.textSize = heroSize
        labelTextPaint.textSize = primarySize
        canvas.drawText(valueStr, heroStart, baseline, speedTextPaint)
        canvas.drawText(unitStr, heroStart + valueWidth, baseline, labelTextPaint)

        // Row 3: "Now XXX km/h"
        labelTextPaint.textSize = secondarySize
        labelTextPaint.textAlign = Paint.Align.CENTER
        baseline += heroFm.descent + gap - secondaryFm.ascent
        canvas.drawText(
            labels.nowSpeedFormat.format(currentSpeedKmh.orDash()),
            cx,
            baseline,
            labelTextPaint,
        )

        speedTextPaint.textAlign = savedSpeedAlign
        labelTextPaint.textAlign = savedLabelAlign
    }

    private fun getStatusColor(state: ZoneState.InZone, speedLimit: Int, currentSpeedKmh: Double?): Int {
        return when {
            state.speedStatus.isOverLimit -> 0xFFEF5350.toInt()
            currentSpeedKmh != null && currentSpeedKmh > speedLimit -> 0xFFFDD835.toInt()
            else -> 0xFF66BB6A.toInt()
        }
    }
}
