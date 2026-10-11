package com.bharat.callassistant.history

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

@Entity(tableName = "calls")
data class CallEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val startedAt: Long,
    val durationSec: Int,
    val roomCode: String,
    val peerName: String,
    val myLanguage: String,
    val peerLanguage: String,
    val avgLatencyMs: Int,
    val maxScam: String,
)

@Dao
interface CallDao {
    @Query("SELECT * FROM calls ORDER BY startedAt DESC")
    fun all(): Flow<List<CallEntity>>

    @Insert
    suspend fun insert(entity: CallEntity)

    @Query("DELETE FROM calls")
    suspend fun clear()
}

@Database(entities = [CallEntity::class], version = 1, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun callDao(): CallDao
}

@Singleton
class RoomHistoryRepository @Inject constructor(private val dao: CallDao) : HistoryRepository {
    override fun entries(): Flow<List<HistoryEntry>> = dao.all().map { list ->
        list.map {
            HistoryEntry(
                it.id, it.startedAt, it.durationSec, it.roomCode, it.peerName,
                it.myLanguage, it.peerLanguage, it.avgLatencyMs, it.maxScam,
            )
        }
    }

    override suspend fun add(entry: HistoryEntry) = dao.insert(
        CallEntity(
            startedAt = entry.startedAt,
            durationSec = entry.durationSec,
            roomCode = entry.roomCode,
            peerName = entry.peerName,
            myLanguage = entry.myLanguage,
            peerLanguage = entry.peerLanguage,
            avgLatencyMs = entry.avgLatencyMs,
            maxScam = entry.maxScam,
        ),
    )

    override suspend fun clear() = dao.clear()
}
