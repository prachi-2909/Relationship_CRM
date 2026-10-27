package com.eko.rcrm.dc.ui.csp

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.data.repository.CspRepository
import com.eko.rcrm.dc.domain.model.PreCall
import com.eko.rcrm.dc.nativecall.NativeCallRequest
import com.eko.rcrm.dc.navigation.Routes
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

data class PreCallUiState(
    val isLoading: Boolean = true,
    val data: PreCall? = null,
    /** Set only when the briefing could not be loaded at all (e.g. the CSP is not this RM's). */
    val error: String? = null,
    /** A commitment action (accept / dismiss / done) is in flight. */
    val busy: Boolean = false,
    val actionError: String? = null
)

@HiltViewModel
class PreCallViewModel @Inject constructor(
    private val cspRepository: CspRepository,
    private val callRepository: CallRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val cspPk: Int = checkNotNull(savedStateHandle[Routes.PRE_CALL_ARG])

    private val _uiState = MutableStateFlow(PreCallUiState())
    val uiState: StateFlow<PreCallUiState> = _uiState.asStateFlow()

    private val _launchNativeCall = MutableSharedFlow<NativeCallRequest>()
    val launchNativeCall: SharedFlow<NativeCallRequest> = _launchNativeCall.asSharedFlow()

    private val _navigateToReview = MutableSharedFlow<Int>()
    val navigateToReview: SharedFlow<Int> = _navigateToReview.asSharedFlow()

    init {
        refresh()
    }

    /** Load (or reload) the briefing. A reload keeps showing the current data until the new one lands. */
    fun refresh() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = it.data == null, error = null) }
            when (val result = cspRepository.getPreCall(cspPk)) {
                is Result.Success -> _uiState.update {
                    it.copy(isLoading = false, data = result.data, error = null)
                }
                is Result.Error -> _uiState.update {
                    // Keep stale data on screen if we have it; only a first load shows a full error.
                    it.copy(isLoading = false, error = if (it.data == null) result.message else null)
                }
            }
        }
    }

    /** status: "open" = accept an AI suggestion, "cancelled" = dismiss it, "done" = completed. */
    fun setStatus(commitmentId: Int, status: String) {
        if (_uiState.value.busy) return
        viewModelScope.launch {
            _uiState.update { it.copy(busy = true, actionError = null) }
            when (val result = cspRepository.setCommitmentStatus(commitmentId, status)) {
                is Result.Success -> {
                    _uiState.update { it.copy(busy = false) }
                    refresh()
                }
                is Result.Error -> _uiState.update { it.copy(busy = false, actionError = result.message) }
            }
        }
    }

    /** Place the call through the app's own outbound flow, exactly as the CSP list does, so it is
     * recorded and tied to this CSP. */
    fun call(number: String) {
        if (number.isBlank()) return
        viewModelScope.launch {
            if (callRepository.hasActiveArmedNativeCall()) {
                _uiState.update { it.copy(actionError = "A call is already in progress. Finish it first.") }
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
                is Result.Error -> _uiState.update { it.copy(actionError = result.message) }
            }
        }
    }
}
