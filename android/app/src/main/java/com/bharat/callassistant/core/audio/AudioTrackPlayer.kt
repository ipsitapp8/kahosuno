package com.bharat.callassistant.core.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import com.bharat.callassistant.core.protocol.SAMPLE_RATE
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/** Streams translated speech to the speaker/earpiece with a low-latency AudioTrack. */
@Singleton
class AudioTrackPlayer @Inject constructor() : SpeechPlayer {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var track: AudioTrack? = null
    private var queue: Channel<ByteArray>? = null
    private var writer: Job? = null

    @Volatile
    private var playingUntilMs = 0L

    @Synchronized
    override fun start() {
        if (track != null) return
        val minBuffer = AudioTrack.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        val audioTrack = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setBufferSizeInBytes(maxOf(minBuffer, SAMPLE_RATE)) // about 0.5 s of headroom
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        audioTrack.play()
        track = audioTrack
        // Writes can block while the buffer is full, so they get their own coroutine and
        // the websocket thread never waits on audio.
        val chunks = Channel<ByteArray>(Channel.UNLIMITED)
        queue = chunks
        writer = scope.launch {
            for (chunk in chunks) {
                audioTrack.write(chunk, 0, chunk.size)
            }
        }
    }

    override fun enqueue(pcm: ByteArray) {
        val q = queue ?: return
        val now = System.currentTimeMillis()
        val durationMs = pcm.size * 1000L / (SAMPLE_RATE * 2)
        playingUntilMs = maxOf(playingUntilMs, now) + durationMs
        q.trySend(pcm)
    }

    override fun isPlaying(): Boolean = System.currentTimeMillis() < playingUntilMs + TAIL_MS

    @Synchronized
    override fun stop() {
        queue?.close()
        writer?.cancel()
        track?.let {
            runCatching { it.pause() }
            runCatching { it.flush() }
            it.release()
        }
        track = null
        queue = null
        writer = null
        playingUntilMs = 0
    }

    private companion object {
        /** Room echo lingers a little after the last sample. */
        const val TAIL_MS = 250L
    }
}
