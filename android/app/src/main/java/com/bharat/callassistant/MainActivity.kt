package com.bharat.callassistant

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.bharat.callassistant.call.CallController
import com.bharat.callassistant.call.CallScreen
import com.bharat.callassistant.history.HistoryScreen
import com.bharat.callassistant.join.JoinScreen
import com.bharat.callassistant.settings.SettingsScreen
import com.bharat.callassistant.settings.SettingsViewModel
import com.bharat.callassistant.ui.KahoSunoTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

private object Routes {
    const val JOIN = "join"
    const val CALL = "call"
    const val HISTORY = "history"
    const val SETTINGS = "settings"
}

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject lateinit var callController: CallController

    private val settingsViewModel: SettingsViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // If a call is still running (service alive, activity was recreated), go back to it.
        val start = if (callController.state.value.isActive) Routes.CALL else Routes.JOIN
        setContent {
            val settings by settingsViewModel.settings.collectAsStateWithLifecycle()
            KahoSunoTheme(fontScale = settings.fontScale) {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val nav = rememberNavController()
                    NavHost(
                        navController = nav,
                        startDestination = start,
                        modifier = Modifier.safeDrawingPadding(),
                    ) {
                        composable(Routes.JOIN) {
                            JoinScreen(
                                onStartCall = { nav.navigate(Routes.CALL) { launchSingleTop = true } },
                                onOpenHistory = { nav.navigate(Routes.HISTORY) },
                                onOpenSettings = { nav.navigate(Routes.SETTINGS) },
                            )
                        }
                        composable(Routes.CALL) {
                            CallScreen(
                                onFinished = {
                                    nav.navigate(Routes.JOIN) {
                                        popUpTo(Routes.JOIN) { inclusive = true }
                                        launchSingleTop = true
                                    }
                                },
                            )
                        }
                        composable(Routes.HISTORY) { HistoryScreen(onBack = { nav.popBackStack() }) }
                        composable(Routes.SETTINGS) { SettingsScreen(onBack = { nav.popBackStack() }) }
                    }
                }
            }
        }
    }
}
