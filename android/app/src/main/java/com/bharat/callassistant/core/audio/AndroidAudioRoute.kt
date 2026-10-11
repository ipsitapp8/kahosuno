package com.bharat.callassistant.core.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Build
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** Voice-call audio mode, audio focus, and speaker / earpiece / Bluetooth headset routing. */
@Singleton
class AndroidAudioRoute @Inject constructor(
    @ApplicationContext context: Context,
) : AudioRoute {
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var focusRequest: AudioFocusRequest? = null

    override fun start(speakerOn: Boolean) {
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .build()
        focusRequest = request
        audioManager.requestAudioFocus(request)
        setSpeaker(speakerOn)
    }

    override fun setSpeaker(on: Boolean) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val devices = audioManager.availableCommunicationDevices
            val target = if (on) {
                devices.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
            } else {
                // Not on speaker: prefer a connected Bluetooth headset, else the earpiece.
                devices.firstOrNull { it.type in BLUETOOTH_TYPES }
                    ?: devices.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_EARPIECE }
            }
            if (target != null) {
                audioManager.setCommunicationDevice(target)
            } else {
                audioManager.clearCommunicationDevice()
            }
        } else {
            @Suppress("DEPRECATION")
            audioManager.isSpeakerphoneOn = on
        }
    }

    override fun stop() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            audioManager.clearCommunicationDevice()
        } else {
            @Suppress("DEPRECATION")
            audioManager.isSpeakerphoneOn = false
        }
        focusRequest?.let { audioManager.abandonAudioFocusRequest(it) }
        focusRequest = null
        audioManager.mode = AudioManager.MODE_NORMAL
    }

    private companion object {
        val BLUETOOTH_TYPES = setOf(
            AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
            AudioDeviceInfo.TYPE_BLE_HEADSET,
        )
    }
}
