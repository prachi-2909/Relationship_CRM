package com.eko.rcrm.dc.ui.officialdetail

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.data.repository.OfficialRepository
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.domain.model.OfficialBriefing
import com.eko.rcrm.dc.domain.model.Suggestion
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

data class OfficialDetailUiState(
    val isLoading: Boolean = true,
    val official: Official? = null,
    val isStartingCall: Boolean = false,
    val error: String? = null,
    /** The relationship briefing; loaded separately so the official's details never wait on it. */
    val briefing: OfficialBriefing? = null,
    val briefingError: String? = null,
    /** A commitment / feedback action is in flight. */
    val busy: Boolean = false
)

@HiltViewModel
class OfficialDetailViewModel @Inject constructor(
    private val officialRepository: OfficialRepository,
    private val callRepository: CallRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    val officialId: Int = checkNotNull(savedStateHandle[Routes.OFFICIAL_DETAIL_ARG])

    private val _uiState = MutableStateFlow(OfficialDetailUiState())
    val uiState: StateFlow<OfficialDetailUiState> = _uiState.asStateFlow()

    private val _navigateToReview = MutableSharedFlow<Int>()
    val navigateToReview: SharedFlow<Int> = _navigateToReview.asSharedFlow()

    private val _launchNativeCall = MutableSharedFlow<NativeCallRequest>()
    val launchNativeCall: SharedFlow<NativeCallRequest> = _launchNativeCall.asSharedFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            when (val result = officialRepository.getOfficial(officialId)) {
                is Result.Success -> _uiState.update { it.copy(isLoading = false, official = result.data) }
                is Result.Error -> _uiState.update { it.copy(isLoading = false, error = result.message) }
            }
        }
        refreshBriefing()
    }

    /** Reload the briefing, keeping what is on screen until the new one lands. */
    fun refreshBriefing() {
        viewModelScope.launch {
            when (val result = officialRepository.getBriefing(officialId)) {
                is Result.Success -> _uiState.update { it.copy(briefing = result.data, briefingError = null) }
                is Result.Error -> _uiState.update {
                    it.copy(briefingError = if (it.briefing == null) result.message else null)
                }
            }
        }
    }

    /** status: "open" = confirm an AI suggestion, "cancelled" = dismiss it / close as not done, "done" =
     * fulfilled; outcome is "fulfilled" / "not_fulfilled" when a live commitment is closed. */
    fun setStatus(commitmentId: Int, status: String, outcome: String? = null) =
        act { officialRepository.setCommitmentStatus(commitmentId, status, outcome) }

    /** decision: "merge" (same commitment) or "separate" (keep both). */
    fun reviewDuplicate(commitmentId: Int, decision: String) =
        act { officialRepository.reviewDuplicate(commitmentId, decision) }

    fun rate(s: Suggestion, verdict: String) =
        act { officialRepository.sendFeedback(officialId, s.type, s.key, verdict) }

    private fun <T> act(block: suspend () -> Result<T>) {
        if (_uiState.value.busy) return
        viewModelScope.launch {
            _uiState.update { it.copy(busy = true, error = null) }
            when (val result = block()) {
                is Result.Success -> {
                    _uiState.update { it.copy(busy = false) }
                    refreshBriefing()
                }
                is Result.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun callOfficial() {
        viewModelScope.launch {
            if (callRepository.hasActiveArmedNativeCall()) {
                _uiState.update { it.copy(error = "A call is already in progress. Finish it before starting another.") }
                return@launch
            }
            _uiState.update { it.copy(isStartingCall = true, error = null) }
            when (val result = callRepository.startOutgoingCall(officialId)) {
                is Result.Success -> {
                    _uiState.update { it.copy(isStartingCall = false) }
                    val call = result.data
                    if (call.isAndroidNative && !call.phoneRef.isNullOrBlank()) {
                        _launchNativeCall.emit(NativeCallRequest(call.id, call.phoneRef))
                    }
                    _navigateToReview.emit(call.id)
                }
                is Result.Error -> _uiState.update { it.copy(isStartingCall = false, error = result.message) }
            }
        }
    }
}
