// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import com.demosten.srednabg.app.ui.util.formatDuration
import com.demosten.srednabg.core.HistoryStats
import com.demosten.srednabg.core.SpeedSample
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.pow

/**
 * Speed-over-time graph for a completed traversal, drawn with a Compose Canvas
 * (no charting dependency). X is time since zone entry, Y is speed in km/h. Three
 * layers: the instantaneous speed curve, the **running average** as a filled band
 * (the app's core metric — it evolves toward the final average, not a flat line),
 * and the zone limit as a dashed reference (constant, so correctly horizontal).
 *
 * A **leading Y axis** (km/h value labels) and a **bottom X axis** (elapsed time
 * as `m:ss`) frame the plot with faint gridlines, matching the iOS Swift Charts
 * `SpeedGraph` (leading `AxisMarks` + time-labelled X `AxisMarks`). `formatDuration`
 * renders the X labels — the same `m:ss` form as the detail header's Duration field
 * and iOS's `elapsedTimeLabel`, so `100 s` reads `1:40`, not an unlabelled number.
 */
@Composable
internal fun SpeedGraph(
    samples: List<SpeedSample>,
    avgSpeedKmh: Double?,
    limitKmh: Int,
    lineColor: Color,
    averageColor: Color,
    limitColor: Color,
    gridColor: Color,
    axisLabelStyle: TextStyle,
    modifier: Modifier = Modifier,
) {
    val textMeasurer = rememberTextMeasurer()
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(200.dp),
    ) {
        if (samples.size < 2) return@Canvas

        val t0 = samples.first().timestampMs
        val tSpanMs = max(1L, samples.last().timestampMs - t0)
        val tSpanSec = tSpanMs / 1000.0

        // Y scale: headroom above whichever is highest — the fastest sample, the
        // limit line, or the average — with a sane floor so a slow zone still
        // renders a readable curve.
        val maxSample = samples.maxOf { it.speedKmh }
        val ceiling = max(max(maxSample, limitKmh.toDouble()), avgSpeedKmh ?: 0.0)
        val maxY = (ceiling * 1.15).coerceAtLeast(20.0).toFloat()

        // Nice, rounded tick values for each axis (Swift Charts picks these for us;
        // here we compute them so labels land on 0 / 20 / 40 … and 0:00 / 0:30 …).
        val yTicks = niceTicks(maxY.toDouble())
        val xTicks = niceTicks(tSpanSec)

        // Pre-measure labels to reserve the axis gutters, so the plot never has to
        // guess how wide the widest km/h label or how tall a time label is.
        val yLabels = yTicks.map { textMeasurer.measure(it.toInt().toString(), axisLabelStyle) }
        val xLabels = xTicks.map {
            textMeasurer.measure(formatDuration((it * 1000).toLong()), axisLabelStyle)
        }
        val labelHeight = (yLabels + xLabels).maxOf { it.size.height }.toFloat()

        val yLabelGap = 6.dp.toPx()
        val xLabelGap = 4.dp.toPx()
        val tickLen = 3.dp.toPx()

        // Plot rectangle, inset for the axis labels. Top pad = half a label so the
        // top-most Y tick label isn't clipped at the frame edge.
        val plotLeft = (yLabels.maxOf { it.size.width }).toFloat() + yLabelGap
        val plotTop = labelHeight / 2f
        val plotRight = size.width
        val plotBottom = size.height - labelHeight - xLabelGap - tickLen
        val plotW = plotRight - plotLeft
        val plotH = plotBottom - plotTop

        fun xOf(tMs: Long): Float = plotLeft + (tMs - t0) / tSpanMs.toFloat() * plotW
        fun yOf(speed: Double): Float = plotBottom - (speed / maxY).toFloat() * plotH

        val faintGrid = gridColor.copy(alpha = 0.4f)

        // Y axis: horizontal gridline + right-aligned km/h label per tick.
        for ((i, tick) in yTicks.withIndex()) {
            val y = yOf(tick)
            drawLine(
                color = faintGrid,
                start = Offset(plotLeft, y),
                end = Offset(plotRight, y),
                strokeWidth = 1.dp.toPx(),
            )
            val label = yLabels[i]
            drawText(
                textLayoutResult = label,
                topLeft = Offset(
                    plotLeft - yLabelGap - label.size.width,
                    y - label.size.height / 2f,
                ),
            )
        }

        // X axis: vertical gridline + tick + centered time label per tick.
        for ((i, tick) in xTicks.withIndex()) {
            val x = plotLeft + (tick / tSpanSec).toFloat() * plotW
            drawLine(
                color = faintGrid,
                start = Offset(x, plotTop),
                end = Offset(x, plotBottom),
                strokeWidth = 1.dp.toPx(),
            )
            drawLine(
                color = gridColor,
                start = Offset(x, plotBottom),
                end = Offset(x, plotBottom + tickLen),
                strokeWidth = 1.dp.toPx(),
            )
            val label = xLabels[i]
            // Clamp so the first (0:00) and last labels stay inside the canvas.
            val labelX = (x - label.size.width / 2f)
                .coerceIn(0f, size.width - label.size.width)
            drawText(
                textLayoutResult = label,
                topLeft = Offset(labelX, plotBottom + tickLen + xLabelGap),
            )
        }

        // Running (cumulative) average as a filled band under its curve. It
        // starts at the first speed and converges toward the final trip average,
        // so it tracks the drive — never a flat line when the speed fluctuates.
        // Drawn first so the axes, limit line, and speed curve sit on top.
        val avgSeries = HistoryStats.runningAverage(samples)
        if (avgSeries.size >= 2) {
            val fill = Path().apply {
                moveTo(xOf(avgSeries.first().timestampMs), plotBottom)
                for (s in avgSeries) lineTo(xOf(s.timestampMs), yOf(s.speedKmh))
                lineTo(xOf(avgSeries.last().timestampMs), plotBottom)
                close()
            }
            drawPath(fill, color = averageColor.copy(alpha = 0.22f))
            // The average curve itself (the top edge of the band).
            val avgLine = Path().apply {
                moveTo(xOf(avgSeries.first().timestampMs), yOf(avgSeries.first().speedKmh))
                for (i in 1 until avgSeries.size) {
                    lineTo(xOf(avgSeries[i].timestampMs), yOf(avgSeries[i].speedKmh))
                }
            }
            drawPath(avgLine, color = averageColor, style = Stroke(width = 2.dp.toPx()))
        }

        // Axis frame (left + bottom), stronger than the interior gridlines.
        drawLine(
            color = gridColor,
            start = Offset(plotLeft, plotTop),
            end = Offset(plotLeft, plotBottom),
            strokeWidth = 1.dp.toPx(),
        )
        drawLine(
            color = gridColor,
            start = Offset(plotLeft, plotBottom),
            end = Offset(plotRight, plotBottom),
            strokeWidth = 1.dp.toPx(),
        )

        // Limit reference line.
        if (limitKmh > 0) {
            val y = yOf(limitKmh.toDouble())
            drawLine(
                color = limitColor,
                start = Offset(plotLeft, y),
                end = Offset(plotRight, y),
                strokeWidth = 2.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 8f)),
            )
        }

        // Speed curve.
        val path = Path().apply {
            moveTo(xOf(samples.first().timestampMs), yOf(samples.first().speedKmh))
            for (i in 1 until samples.size) {
                lineTo(xOf(samples[i].timestampMs), yOf(samples[i].speedKmh))
            }
        }
        drawPath(
            path = path,
            color = lineColor,
            style = Stroke(width = 2.5.dp.toPx()),
        )
    }
}

/**
 * Rounded, human-friendly tick values from 0 up to (and not past) [max], aiming
 * for about [target] intervals — the "nice numbers" an axis wants (…, 20, 50,
 * 100). Mirrors what Swift Charts computes automatically on iOS.
 */
private fun niceTicks(max: Double, target: Int = 4): List<Double> {
    if (max <= 0.0) return listOf(0.0)
    val rawStep = max / target
    val magnitude = 10.0.pow(floor(log10(rawStep)))
    val residual = rawStep / magnitude
    val step = when {
        residual <= 1.0 -> 1.0
        residual <= 2.0 -> 2.0
        residual <= 5.0 -> 5.0
        else -> 10.0
    } * magnitude
    val ticks = mutableListOf<Double>()
    var v = 0.0
    while (v <= max + step * 1e-6) {
        ticks.add(v)
        v += step
    }
    return ticks
}
