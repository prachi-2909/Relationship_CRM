package com.eko.rcrm.dc.ui.manualdial

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.nativecall.NativeCallRequest
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ManualDialUiState(
    val number: String = "",
    val isCalling: Boolean = false,
    val error: String? = null
)

/** The dial pad calls out exactly like calling a saved official (POST /calls/outgoing) - the
 * backend decides whether that's Knowlarity or this device's own SIM (channel in the
 * response); android_native hands off to the native dialer via launchNativeCall below. */
@HiltViewModel
class ManualDialViewModel @Inject constructor(
    private val callRepository: CallRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(ManualDialUiState())
    val uiState: StateFlow<ManualDialUiState> = _uiState.asStateFlow()

    private val _navigateToReview = MutableSharedFlow<Int>()
    val navigateToReview: SharedFlow<Int> = _navigateToReview.asSharedFlow()

    private val _launchNativeCall = MutableSharedFlow<NativeCallRequest>()
    val launchNativeCall: SharedFlow<NativeCallRequest> = _launchNativeCall.asSharedFlow()

    fun onNumberChange(value: String) {
        _uiState.update { it.copy(number = value.filter { c -> c.isDigit() }.take(15), error = null) }
    }

    fun call() {
        val number = _uiState.value.number
        if (number.length < 10) {
            _uiState.update { it.copy(error = "Enter a valid phone number") }
            return
        }
        viewModelScope.launch {
            if (callRepository.hasActiveArmedNativeCall()) {
                _uiState.update { it.copy(error = "A call is already in progress. Finish it before starting another.") }
                return@launch
            }
            _uiState.update { it.copy(isCalling = true, error = null) }
            when (val result = callRepository.startManualCall(number)) {
                is Result.Success -> {
                    _uiState.update { it.copy(isCalling = false) }
                    val call = result.data
                    if (call.isAndroidNative && !call.phoneRef.isNullOrBlank()) {
                        _launchNativeCall.emit(NativeCallRequest(call.id, call.phoneRef))
                    }
                    _navigateToReview.emit(call.id)
                }
                is Result.Error -> _uiState.update { it.copy(isCalling = false, error = result.message) }
            }
        }
    }
}
