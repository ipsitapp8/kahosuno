package com.bharat.callassistant.call

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.bharat.callassistant.MainActivity
import com.bharat.callassistant.R
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Keeps the call alive when the screen is off. The session does the work; this service holds
 * the foreground notification (required for microphone use in the background) and stops
 * itself when the call ends.
 */
@AndroidEntryPoint
class CallService : Service() {
    @Inject lateinit var session: CallSession

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_HANG_UP) {
            session.hangUp()
            stopSelf()
            return START_NOT_STICKY
        }
        startInForeground()
        session.start()
        watcher?.cancel()
        watcher = scope.launch {
            session.state.first { it.phase == Phase.Ended }
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        // The user swiped the app away or the system stopped us: do not leave a call running.
        if (session.state.value.isActive) session.hangUp()
        scope.cancel()
        super.onDestroy()
    }

    private fun startInForeground() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel),
                NotificationManager.IMPORTANCE_LOW,
            ),
        )
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val hangUp = PendingIntent.getService(
            this,
            1,
            Intent(this, CallService::class.java).setAction(ACTION_HANG_UP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.sym_action_call)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(getString(R.string.notification_text))
            .setContentIntent(open)
            .addAction(0, getString(R.string.notification_hang_up), hangUp)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    companion object {
        private const val CHANNEL_ID = "call"
        private const val NOTIFICATION_ID = 1
        const val ACTION_HANG_UP = "com.bharat.callassistant.HANG_UP"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, CallService::class.java))
        }
    }
}
