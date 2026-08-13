// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.remote

import com.demosten.srednabg.BuildConfig
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * The data-feed suffix rule and the retired-feed flag.
 *
 * Worth pinning because getting the suffix wrong is *silent*: a build pointed
 * at the wrong feed still receives a well-formed payload and syncs it happily,
 * so nothing downstream reports a problem — the user simply gets somebody
 * else's zone data. The feed-1 cases are the load-bearing ones; every install
 * ever published fetches those two bare paths.
 *
 * Swift twin: `BackendURLsTests`.
 */
class ZoneApiFeedTest {

    @Test
    fun `feed 1 has no suffix`() {
        assertEquals("/api/zones", ZoneApi.endpointPath("zones", 1))
        assertEquals("/api/version", ZoneApi.endpointPath("version", 1))
    }

    @Test
    fun `later feeds are suffixed`() {
        assertEquals("/api/zones.2", ZoneApi.endpointPath("zones", 2))
        assertEquals("/api/version.12", ZoneApi.endpointPath("version", 12))
    }

    @Test
    fun `endpoints follow the compiled feed`() {
        val suffix = if (BuildConfig.ZONE_FEED_VERSION == 1) "" else ".${BuildConfig.ZONE_FEED_VERSION}"
        assertEquals("${ZoneApi.BASE_URL}/api/zones$suffix", ZoneApi.endpoint("zones"))
        assertEquals("${ZoneApi.BASE_URL}/api/version$suffix", ZoneApi.endpoint("version"))
    }

    /**
     * Kept in sync with `scrapers/contracts/manifest.json` and the Feed column
     * in VERSIONS.md. If this fails, the change was deliberate — update those
     * two as well, and check `prepareZonesAsset` still finds `zones.N.json`.
     */
    @Test
    fun `this build is on feed 1`() {
        assertEquals(1, BuildConfig.ZONE_FEED_VERSION)
    }

    // `unsupported` — any non-zero value means "tell the user to update". It is
    // an Int rather than a Boolean so a future `true` on the wire decodes too;
    // these cases pin that the absent case stays the quiet, supported default.
    @Test
    fun `absent unsupported flag means supported`() {
        assertFalse(version(unsupported = null).isFeedUnsupported)
    }

    @Test
    fun `zero means supported`() {
        assertFalse(version(unsupported = 0).isFeedUnsupported)
    }

    @Test
    fun `any non-zero value means unsupported`() {
        assertTrue(version(unsupported = 1).isFeedUnsupported)
        assertTrue(version(unsupported = 2).isFeedUnsupported)
    }

    private fun version(unsupported: Int?) = VersionResponse(
        version = "2026-04-12T10:00:00Z",
        hash = "sha256:abc",
        unsupported = unsupported,
    )
}
