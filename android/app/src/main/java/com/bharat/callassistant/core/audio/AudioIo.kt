package com.bharat.callassistant.core.audio

import com.bharat.callassistant.core.protocol.ScamLevel
import kotlinx.coroutines.flow.Flow

/** 16 kHz mono PCM16 microphone chunks of [com.bharat.callassistant.core.protocol.FRAME_BYTES]. */
interface MicSource {
    /** Cold flow: starts recording when collected, releases the microphone when cancelled. */
    fun frames(): Flow<ByteArray>
}

/** Plays translated speech (16 kHz mono PCM16) as it arrives. */
interface SpeechPlayer {
    fun start()
    fun enqueue(pcm: ByteArray)
    fun stop()

    /** True while queued speech is still being played. Used to avoid hearing ourselves. */
    fun isPlaying(): Boolean
}

/** Audio focus and earpiece / speaker / Bluetooth routing for a voice call. */
interface AudioRoute {
    fun start(speakerOn: Boolean)
    fun setSpeaker(on: Boolean)
    fun stop()
}

/** Phone vibration for scam warnings. */
interface Haptics {
    fun warn(level: ScamLevel)
}
