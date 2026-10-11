package com.bharat.callassistant

import com.bharat.callassistant.call.CallUiState
import com.bharat.callassistant.call.CallViewModel
import com.bharat.callassistant.call.Phase
import com.bharat.callassistant.core.network.ApiException
import com.bharat.callassistant.core.protocol.TalkMode
import com.bharat.callassistant.join.JoinError
import com.bharat.callassistant.join.JoinEvent
import com.bharat.callassistant.join.JoinMode
import com.bharat.callassistant.join.JoinViewModel
import com.bharat.callassistant.settings.AppSettings
import com.bharat.callassistant.settings.MAX_FONT_SCALE
import com.bharat.callassistant.settings.MIN_FONT_SCALE
import com.bharat.callassistant.settings.SettingsViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class JoinViewModelTest {
    private val api = FakeRoomApi()
    private val settings = FakeSettings(AppSettings(serverUrl = "https://calls.example.com", mode = TalkMode.PushToTalk))
    private val starter = FakeStarter()
    private lateinit var vm: JoinViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        vm = JoinViewModel(api, settings, starter)
    }

    @After
    fun tearDown() = Dispatchers.resetMain()

    private fun ready(name: String = "Ramesh", mode: JoinMode = JoinMode.NewRoom, code: String = "") {
        vm.setName(name)
        vm.setJoinMode(mode)
        vm.setCode(code)
        vm.setConsent(true)
    }

    @Test
    fun `empty name is rejected before any network call`() {
        vm.setName("   ")
        vm.setConsent(true)
        vm.submit()
        assertEquals(JoinError.NameEmpty, vm.state.value.error)
        assertTrue(api.calls.isEmpty())
    }

    @Test
    fun `consent is required`() {
        vm.setName("Ramesh")
        vm.submit()
        assertEquals(JoinError.ConsentMissing, vm.state.value.error)
        assertTrue(api.calls.isEmpty())
    }

    @Test
    fun `joining needs a six digit code`() {
        ready(mode = JoinMode.JoinRoom, code = "123")
        vm.submit()
        assertEquals(JoinError.CodeInvalid, vm.state.value.error)
        assertTrue(api.calls.isEmpty())
    }

    @Test
    fun `code field keeps only six digits`() {
        vm.setCode("12a34-56789")
        assertEquals("123456", vm.state.value.code)
    }

    @Test
    fun `editing clears the previous error`() {
        vm.submit()
        assertNotNull(vm.state.value.error)
        vm.setName("R")
        assertNull(vm.state.value.error)
    }

    @Test
    fun `creating a room prepares the call and fires the start event`() = runTest(UnconfinedTestDispatcher()) {
        val events = mutableListOf<JoinEvent>()
        val job = launch { vm.events.collect { events += it } }
        ready(name = "  Ramesh  ")
        vm.setLanguage("kn-IN")

        vm.submit()

        assertEquals(listOf("create|https://calls.example.com|Ramesh|kn-IN"), api.calls)
        val p = starter.prepared!!
        assertEquals("room-1", p.roomId)
        assertEquals("123456", p.code)
        assertEquals("tok-1", p.token)
        assertEquals("Ramesh", p.name)
        assertEquals("kn-IN", p.language)
        assertEquals("https://calls.example.com", p.serverUrl)
        assertEquals(TalkMode.PushToTalk, p.mode) // default mode comes from Settings
        assertEquals(listOf<JoinEvent>(JoinEvent.StartCall), events)
        assertFalse(vm.state.value.loading)
        job.cancel()
    }

    @Test
    fun `joining with a code calls the join endpoint`() {
        ready(mode = JoinMode.JoinRoom, code = "654321")
        vm.setLanguage("hi-IN")
        vm.submit()
        assertEquals(listOf("join|https://calls.example.com|654321|Ramesh|hi-IN"), api.calls)
        assertNotNull(starter.prepared)
    }

    @Test
    fun `name and language are remembered for next time`() {
        ready()
        vm.setLanguage("hi-IN")
        vm.submit()
        assertEquals("Ramesh", settings.value.name)
        assertEquals("hi-IN", settings.value.language)
    }

    @Test
    fun `the form is pre-filled from saved settings`() {
        val saved = FakeSettings(AppSettings(name = "Sita", language = "hi-IN"))
        val fresh = JoinViewModel(api, saved, starter)
        assertEquals("Sita", fresh.state.value.name)
        assertEquals("hi-IN", fresh.state.value.language)
    }

    @Test
    fun `unreachable server shows a network error and stays on the form`() {
        ready()
        api.failure = ApiException(ApiException.NETWORK, "timeout")
        vm.submit()
        assertEquals(JoinError.Network, vm.state.value.error)
        assertNull(starter.prepared)
        assertFalse(vm.state.value.loading)
    }

    @Test
    fun `server rejection shows the server message`() {
        ready(mode = JoinMode.JoinRoom, code = "111111")
        api.failure = ApiException("room_full", "Room already has two participants")
        vm.submit()
        assertEquals(JoinError.Server, vm.state.value.error)
        assertEquals("Room already has two participants", vm.state.value.errorDetail)
        assertNull(starter.prepared)
    }

    @Test
    fun `can retry after a failure`() {
        ready()
        api.failure = ApiException(ApiException.NETWORK, "x")
        vm.submit()
        api.failure = null
        vm.submit()
        assertNull(vm.state.value.error)
        assertNotNull(starter.prepared)
        assertEquals(2, api.calls.size)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class CallViewModelTest {
    private val controller = FakeController()
    private val vm = CallViewModel(controller)

    @Test
    fun `state comes straight from the call controller`() {
        controller.set(CallUiState(phase = Phase.InCall, muted = true))
        assertEquals(Phase.InCall, vm.state.value.phase)
        assertTrue(vm.state.value.muted)
    }

    @Test
    fun `toggles flip the current value`() {
        controller.set(CallUiState(muted = false, speakerOn = true))
        vm.toggleMute()
        vm.toggleSpeaker()
        controller.set(CallUiState(muted = true, speakerOn = false))
        vm.toggleMute()
        vm.toggleSpeaker()
        assertEquals(listOf("muted=true", "speaker=false", "muted=false", "speaker=true"), controller.log)
    }

    @Test
    fun `actions are forwarded`() {
        vm.setMode(TalkMode.PushToTalk)
        vm.pttPressed(true)
        vm.pttPressed(false)
        vm.dismissScam()
        vm.hangUp()
        assertEquals(listOf("mode=ptt", "ptt=true", "ptt=false", "dismiss", "hangUp"), controller.log)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {
    private val store = FakeSettings()

    @Before
    fun setUp() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `changes are saved`() {
        val vm = SettingsViewModel(store)
        vm.setServerUrl("  https://x.onrender.com ")
        vm.setMode(TalkMode.PushToTalk)
        vm.setFontScale(1.3f)
        assertEquals("https://x.onrender.com", store.value.serverUrl)
        assertEquals(TalkMode.PushToTalk, store.value.mode)
        assertEquals(1.3f, store.value.fontScale, 0.001f)
        assertEquals(1.3f, vm.settings.value.fontScale, 0.001f)
    }

    @Test
    fun `font size is kept within a sane range`() {
        val vm = SettingsViewModel(store)
        vm.setFontScale(5f)
        assertEquals(MAX_FONT_SCALE, store.value.fontScale, 0.001f)
        vm.setFontScale(0.1f)
        assertEquals(MIN_FONT_SCALE, store.value.fontScale, 0.001f)
    }
}
