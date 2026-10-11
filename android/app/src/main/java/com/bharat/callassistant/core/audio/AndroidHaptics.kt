package com.bharat.callassistant.core.audio

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import com.bharat.callassistant.core.protocol.ScamLevel
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AndroidHaptics @Inject constructor(
    @ApplicationContext private val context: Context,
) : Haptics {
    private val vibrator: Vibrator? by lazy {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager)
                ?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
    }

    override fun warn(level: ScamLevel) {
        val v = vibrator ?: return
        if (!v.hasVibrator()) return
        val pattern = when (level) {
            ScamLevel.High -> longArrayOf(0, 700, 200, 700, 200, 700, 200, 700) // strong, long
            ScamLevel.Suspicious -> longArrayOf(0, 350, 200, 350)
            ScamLevel.None -> return
        }
        v.vibrate(VibrationEffect.createWaveform(pattern, -1))
    }
}
