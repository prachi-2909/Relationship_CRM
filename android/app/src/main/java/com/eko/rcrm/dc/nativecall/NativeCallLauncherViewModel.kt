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
}
