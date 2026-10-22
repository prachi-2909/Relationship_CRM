package com.eko.rcrm.dc.ui.csp

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CspRepository
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.domain.model.Csp
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

data class CspListUiState(
    val items: List<Csp> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null
)

@HiltViewModel
class CspListViewModel @Inject constructor(
    private val cspRepository: CspRepository,
    private val callRepository: CallRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(CspListUiState())
    val uiState: StateFlow<CspListUiState> = _uiState.asStateFlow()

    private val _launchNativeCall = MutableSharedFlow<NativeCallRequest>()
    val launchNativeCall: SharedFlow<NativeCallRequest> = _launchNativeCall.asSharedFlow()

    private val _navigateToReview = MutableSharedFlow<Int>()
    val navigateToReview: SharedFlow<Int> = _navigateToReview.asSharedFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            when (val result = cspRepository.getMyCsps()) {
                is Result.Success -> _uiState.update { it.copy(isLoading = false, items = result.data) }
                is Result.Error -> _uiState.update { it.copy(isLoading = false, error = result.message) }
            }
        }
    }

    /** Place a call to a CSP through the app's own outbound flow (POST /calls/outgoing +
     * NativeCallForegroundService), NOT the plain dialer - that path reliably captures the number
     * and records both sides. A dialer-only ACTION_DIAL would often lose the number and record
     * nothing for an outgoing call. */
    fun call(number: String) {
        if (number.isBlank()) return
        viewModelScope.launch {
            if (callRepository.hasActiveArmedNativeCall()) {
                _uiState.update { it.copy(error = "A call is already in progress. Finish it first.") }
                return@launch
            }
            when (val result = callRepository.startManualCall(number)) {
                is Result.Success -> {
                    val callSession = result.data
                    if (callSession.isAndroidNative && !callSession.phoneRef.isNullOrBlank()) {
                        _launchNativeCall.emit(NativeCallRequest(callSession.id, callSession.phoneRef))
                    }
                    _navigateToReview.emit(callSession.id)
                }
                is Result.Error -> _uiState.update { it.copy(error = result.message) }
            }
        }
    }
}
