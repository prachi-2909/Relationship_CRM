package com.eko.rcrm.dc.ui.recording

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.local.CallRecordingPrefs
import com.eko.rcrm.dc.data.local.PrivilegedMode
import com.eko.rcrm.dc.nativecall.recording.RecordingCapability
import com.eko.rcrm.dc.nativecall.recording.RecordingEngineProvider
import com.eko.rcrm.dc.recorder.AdbPairingService
import com.eko.rcrm.dc.recorder.EmbeddedAdb
import com.eko.rcrm.dc.recorder.RecorderBackend
import com.eko.rcrm.dc.recorder.ShizukuBackend
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject

data class EngineCapabilityRow(val engineId: String, val isActive: Boolean, val capability: RecordingCapability)

/** Backs the Recording Capability screen: shows which engine is active and why, lets the DC pick the
 * privilege source for two-way recording, and drives the built-in (embedded ADB) pairing or the
 * Shizuku permission. */
@HiltViewModel
class RecordingCapabilityViewModel @Inject constructor(
    private val provider: RecordingEngineProvider,
    private val callRecordingPrefs: CallRecordingPrefs,
    @ApplicationContext private val context: Context
) : ViewModel() {

    fun snapshot(): List<EngineCapabilityRow> {
        val active = provider.currentEngine()
        return provider.allEngines().map { engine ->
            EngineCapabilityRow(engine.id, engine === active, engine.getCapability())
        }
    }

    fun mode(): PrivilegedMode = callRecordingPrefs.privilegedMode

    fun setMode(mode: PrivilegedMode) { callRecordingPrefs.privilegedMode = mode }

    fun readiness(): RecorderBackend.Readiness = RecorderBackend.readiness(context, callRecordingPrefs.privilegedMode)

    fun requestShizukuPermission() = ShizukuBackend.requestPermission()

    /** Starts the notification-driven pairing: the DC enters the 6-digit code in the notification,
     * without leaving the Settings pairing popup (which would cancel it). */
    fun startEmbeddedPairing() = AdbPairingService.start(context)

    /** Arms off-Wi-Fi recording (classic-tcpip loopback). [onResult] gets a message; runs off-main. */
    fun armOffWifi(onResult: (Boolean, String) -> Unit) {
        viewModelScope.launch {
            val ok = withContext(Dispatchers.IO) { EmbeddedAdb.armOffWifi(context) }
            onResult(
                ok,
                if (ok) "Off-Wi-Fi recording armed. Works without Wi-Fi until the phone reboots."
                else "Could not arm. Turn on Wi-Fi + Wireless debugging once, and keep USB debugging ON, then retry."
            )
        }
    }
}
