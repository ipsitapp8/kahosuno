package com.bharat.callassistant.history

import kotlinx.coroutines.flow.Flow

/** One finished call. Metadata only: never audio, never what was said. */
data class HistoryEntry(
    val id: Long = 0,
    val startedAt: Long,
    val durationSec: Int,
    val roomCode: String,
    val peerName: String,
    val myLanguage: String,
    val peerLanguage: String,
    val avgLatencyMs: Int,
    /** "none", "suspicious" or "high": the strongest scam warning shown during the call. */
    val maxScam: String,
)

interface HistoryRepository {
    fun entries(): Flow<List<HistoryEntry>>
    suspend fun add(entry: HistoryEntry)
    suspend fun clear()
}
