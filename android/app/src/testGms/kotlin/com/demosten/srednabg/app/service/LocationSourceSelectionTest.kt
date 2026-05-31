// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app (gms flavor unit tests)

package com.demosten.srednabg.app.service

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.CsvSource

/**
 * Covers the gms flavor's runtime fallback policy ([chooseLocationSourceKind]).
 * FusedLocationProvider must be chosen only on a non-automotive device with
 * working Play Services; every other combination must fall back to the
 * platform LocationManager so the app never silently stops getting fixes.
 */
class LocationSourceSelectionTest {

    @Test
    fun `fused only on a phone with working play services`() {
        assertEquals(
            LocationSourceKind.FUSED,
            chooseLocationSourceKind(isAutomotive = false, isGmsAvailable = true),
        )
    }

    @ParameterizedTest(name = "automotive={0}, gmsAvailable={1} -> SYSTEM")
    @CsvSource(
        "true, true",   // automotive: FLP unreliable on AAOS
        "true, false",  // automotive + no GMS
        "false, false", // de-Googled / disabled / outdated Play Services
    )
    fun `falls back to system in every other case`(
        isAutomotive: Boolean,
        isGmsAvailable: Boolean,
    ) {
        assertEquals(
            LocationSourceKind.SYSTEM,
            chooseLocationSourceKind(isAutomotive, isGmsAvailable),
        )
    }
}
