package com.eko.rcrm.dc.nativecall

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Thin Hilt-scoped handle onto CallRepository for the Compose-side launcher below, which
 * isn't itself a ViewModel and has no other way to reach a Hilt-provided dependency. */
@HiltViewModel
class NativeCallLauncherViewModel @Inject constructor(
    private val callRepository: CallRepository
) : ViewModel() {

    fun arm(callSessionId: Int, phone: String) {
        viewModelScope.launch { callRepository.armNativeCall(callSessionId, phone) }
    }

    /** The call was registered with the server but never placed (permission refused, no dialer to open).
     * Reports it as not connected so the session is cancelled instead of sitting in Pending as a call that
     * never happened, and frees the single-flight slot so the next call is not refused. */
    fun cancel(callSessionId: Int) {
        viewModelScope.launch {
            callRepository.completeNativeCall(
                callId = callSessionId,
                endedAtIso = java.time.Instant.now().toString(),
                durationSeconds = 0,
                connected = false
            )
            callRepository.clearArmedNativeCall()
        }
    }
}
