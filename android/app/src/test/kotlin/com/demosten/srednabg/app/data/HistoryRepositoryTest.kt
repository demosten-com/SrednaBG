// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class HistoryRepositoryTest {

    private val dao = FakeZoneTraversalDao()
    private val repo = HistoryRepository(dao)

    private val now = 1_800_000_000_000L
    private val dayMs = 24L * 60 * 60 * 1000

    @Test
    fun `record and observe round-trips`() = runTest {
        repo.record(traversalEntity("a", exitTimeMs = now))
        assertEquals(1, repo.count())
        assertEquals("a", repo.observeAll().first().single().id)
        assertEquals("a", repo.getById("a")?.id)
    }

    @Test
    fun `prune none clears everything`() = runTest {
        repo.record(traversalEntity("a", exitTimeMs = now))
        repo.record(traversalEntity("b", exitTimeMs = now - dayMs))
        repo.prune(HistoryRetention.NONE, nowMs = now)
        assertEquals(0, repo.count())
    }

    @Test
    fun `prune 1 month drops records older than 30 days and keeps newer`() = runTest {
        repo.record(traversalEntity("recent", exitTimeMs = now - 10 * dayMs))
        repo.record(traversalEntity("old", exitTimeMs = now - 40 * dayMs))
        repo.prune(HistoryRetention.ONE_MONTH, nowMs = now)
        val ids = repo.observeAll().first().map { it.id }
        assertEquals(listOf("recent"), ids)
    }

    @Test
    fun `prune 3 months keeps a 60-day-old record`() = runTest {
        repo.record(traversalEntity("twoMonths", exitTimeMs = now - 60 * dayMs))
        repo.prune(HistoryRetention.THREE_MONTHS, nowMs = now)
        assertEquals(1, repo.count())
    }

    @Test
    fun `latest returns the most recently exited`() = runTest {
        repo.record(traversalEntity("old", exitTimeMs = now - dayMs))
        repo.record(traversalEntity("new", exitTimeMs = now))
        assertEquals("new", repo.latest()?.id)
    }

    @Test
    fun `clearAll empties the store`() = runTest {
        repo.record(traversalEntity("a", exitTimeMs = now))
        repo.clearAll()
        assertNull(repo.latest())
        assertTrue(repo.observeAll().first().isEmpty())
    }

    @Test
    fun `retention setting mapping is stable`() {
        assertEquals(HistoryRetention.NONE, HistoryRetention.fromSetting("none"))
        assertEquals(HistoryRetention.ONE_MONTH, HistoryRetention.fromSetting("1month"))
        assertEquals(HistoryRetention.THREE_MONTHS, HistoryRetention.fromSetting("3months"))
        assertEquals(HistoryRetention.SIX_MONTHS, HistoryRetention.fromSetting("6months"))
        // Unknown / legacy value falls back to the default (3 months).
        assertEquals(HistoryRetention.DEFAULT, HistoryRetention.fromSetting("bogus"))
    }
}
