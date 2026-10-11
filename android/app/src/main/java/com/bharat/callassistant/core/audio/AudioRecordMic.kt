package com.bharat.callassistant.core.audio

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import com.bharat.callassistant.core.protocol.FRAME_BYTES
import com.bharat.callassistant.core.protocol.SAMPLE_RATE
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.isActive
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/** Microphone via AudioRecord with the VOICE_COMMUNICATION source (echo cancellation friendly). */
@Singleton
class AudioRecordMic @Inject constructor() : MicSource {

    @SuppressLint("MissingPermission") // RECORD_AUDIO is requested on the join screen first
    override fun frames(): Flow<ByteArray> = flow {
        val minBuffer = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        val record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minBuffer, FRAME_BYTES * 4),
        )
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            throw IOException("Microphone could not be opened")
        }
        val echo = if (AcousticEchoCanceler.isAvailable()) {
            AcousticEchoCanceler.create(record.audioSessionId)?.also { it.enabled = true }
        } else {
            null
        }
        val noise = if (NoiseSuppressor.isAvailable()) {
            NoiseSuppressor.create(record.audioSessionId)?.also { it.enabled = true }
        } else {
            null
        }
        try {
            record.startRecording()
            val buffer = ByteArray(FRAME_BYTES)
            while (currentCoroutineContext().isActive) {
                var filled = 0
                while (filled < FRAME_BYTES) {
                    val n = record.read(buffer, filled, FRAME_BYTES - filled)
                    if (n < 0) throw IOException("Microphone read failed ($n)")
                    filled += n
                }
                emit(buffer.copyOf())
            }
        } finally {
            echo?.release()
            noise?.release()
            runCatching { record.stop() }
            record.release()
        }
    }.flowOn(Dispatchers.IO)
}
