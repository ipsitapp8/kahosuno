package com.bharat.callassistant.di

import android.content.Context
import androidx.room.Room
import com.bharat.callassistant.call.CallController
import com.bharat.callassistant.call.CallSession
import com.bharat.callassistant.call.CallStarter
import com.bharat.callassistant.core.audio.AndroidAudioRoute
import com.bharat.callassistant.core.audio.AndroidHaptics
import com.bharat.callassistant.core.audio.AudioRecordMic
import com.bharat.callassistant.core.audio.AudioRoute
import com.bharat.callassistant.core.audio.AudioTrackPlayer
import com.bharat.callassistant.core.audio.Haptics
import com.bharat.callassistant.core.audio.MicSource
import com.bharat.callassistant.core.audio.SpeechPlayer
import com.bharat.callassistant.core.network.HttpRoomApi
import com.bharat.callassistant.core.network.OkHttpTransport
import com.bharat.callassistant.core.network.RoomApi
import com.bharat.callassistant.core.network.Transport
import com.bharat.callassistant.history.AppDatabase
import com.bharat.callassistant.history.CallDao
import com.bharat.callassistant.history.HistoryRepository
import com.bharat.callassistant.history.RoomHistoryRepository
import com.bharat.callassistant.settings.DataStoreSettings
import com.bharat.callassistant.settings.SettingsStore
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class BindingsModule {
    @Binds abstract fun transport(impl: OkHttpTransport): Transport
    @Binds abstract fun roomApi(impl: HttpRoomApi): RoomApi
    @Binds abstract fun settings(impl: DataStoreSettings): SettingsStore
    @Binds abstract fun history(impl: RoomHistoryRepository): HistoryRepository
    @Binds abstract fun mic(impl: AudioRecordMic): MicSource
    @Binds abstract fun player(impl: AudioTrackPlayer): SpeechPlayer
    @Binds abstract fun route(impl: AndroidAudioRoute): AudioRoute
    @Binds abstract fun haptics(impl: AndroidHaptics): Haptics
}

@Module
@InstallIn(SingletonComponent::class)
object ProvidersModule {
    @Provides
    @Singleton
    fun okHttp(): OkHttpClient = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS) // keeps the websocket alive through proxies
        .connectTimeout(20, TimeUnit.SECONDS)
        .build()

    @Provides
    @Singleton
    fun database(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, "history.db").build()

    @Provides
    fun callDao(db: AppDatabase): CallDao = db.callDao()

    @Provides
    @Singleton
    fun callSession(
        transport: Transport,
        mic: MicSource,
        player: SpeechPlayer,
        route: AudioRoute,
        haptics: Haptics,
        history: HistoryRepository,
    ): CallSession = CallSession(
        transport = transport,
        mic = mic,
        player = player,
        route = route,
        haptics = haptics,
        history = history,
        scope = CoroutineScope(SupervisorJob() + Dispatchers.Default),
    )

    @Provides
    fun callController(session: CallSession): CallController = session

    @Provides
    fun callStarter(session: CallSession): CallStarter = session
}
