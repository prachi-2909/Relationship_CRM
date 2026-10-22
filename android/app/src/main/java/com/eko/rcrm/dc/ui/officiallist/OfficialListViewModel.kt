package com.eko.rcrm.dc.ui.officiallist

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.data.repository.OfficialRepository
import com.eko.rcrm.dc.domain.model.Official
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
import java.net.URLDecoder
import javax.inject.Inject

data class OfficialListUiState(
    val unitName: String? = null,
    val officials: List<Official> = emptyList(),
    val isLoading: Boolean = true,
    val isStartingCall: Boolean = false,
    val error: String? = null
)

@HiltViewModel
class OfficialListViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val officialRepository: OfficialRepository,
    private val callRepository: CallRepository
) : ViewModel() {

    private val unitId: Int? = savedStateHandle.get<Int>(Routes.OFFICIAL_LIST_UNIT_ID_ARG)?.takeIf { it > 0 }
    private val unitNameArg: String? = savedStateHandle.get<String>(Routes.OFFICIAL_LIST_UNIT_NAME_ARG)
        ?.let { runCatching { URLDecoder.decode(it, "UTF-8") }.getOrNull() }

    private val _uiState = MutableStateFlow(OfficialListUiState(unitName = unitNameArg))
    val uiState: StateFlow<OfficialListUiState> = _uiState.asStateFlow()

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
            when (val result = officialRepository.list(unitId = unitId)) {
                is Result.Success -> _uiState.update { it.copy(isLoading = false, officials = result.data) }
                is Result.Error -> _uiState.update { it.copy(isLoading = false, error = result.message) }
            }
        }
    }

    fun callOfficial(official: Official) {
        viewModelScope.launch {
            if (callRepository.hasActiveArmedNativeCall()) {
                _uiState.update { it.copy(error = "A call is already in progress. Finish it before starting another.") }
                return@launch
            }
            _uiState.update { it.copy(isStartingCall = true, error = null) }
            when (val result = callRepository.startOutgoingCall(official.id)) {
                is Result.Success -> {
                    _uiState.update { it.copy(isStartingCall = false) }
                    val call = result.data
                    if (call.isAndroidNative && !call.phoneRef.isNullOrBlank()) {
                        _launchNativeCall.emit(NativeCallRequest(call.id, call.phoneRef))
                    }
                    _navigateToReview.emit(call.id)
                }
                is Result.Error -> _uiState.update {
                    it.copy(isStartingCall = false, error = result.message)
                }
            }
        }
    }
}
