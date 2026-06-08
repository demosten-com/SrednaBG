// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.overlay

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.app.ui.components.ZoneStatusChip
import com.demosten.srednabg.app.ui.components.ZoneStatusPill
import com.demosten.srednabg.core.ZoneState

/**
 * Content of the floating system overlay window. Observes the same companion
 * StateFlows the in-app UI uses — no extra plumbing — and swaps between the
 * compact [ZoneStatusPill] (Outside) and the full [ZoneStatusChip] (InZone /
 * Exiting). The swap is instant — the `WRAP_CONTENT` overlay window resizes to
 * match on the next layout pass (animating the content size inside a
 * WindowManager window looked choppy, so it's deliberately omitted).
 *
 * [modifier] carries the drag handling supplied by `OverlayController`.
 */
@Composable
internal fun OverlayContent(
    debugMaxSpeedOverride: Int?,
    modifier: Modifier = Modifier,
) {
    val state by LocationTrackingService.zoneState.collectAsStateWithLifecycle()
    val position by LocationTrackingService.currentPosition.collectAsStateWithLifecycle()
    val speed = position?.speed

    Box(modifier = modifier) {
        when (state) {
            is ZoneState.Outside -> ZoneStatusPill(currentSpeedKmh = speed)
            else -> ZoneStatusChip(
                state = state,
                currentSpeedKmh = speed,
                debugMaxSpeedOverride = debugMaxSpeedOverride,
            )
        }
    }
}
