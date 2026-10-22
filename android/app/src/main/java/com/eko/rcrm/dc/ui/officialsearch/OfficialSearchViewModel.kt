package com.eko.rcrm.dc.ui.officialsearch

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.data.repository.OfficialRepository
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.nativecall.NativeCallRequest
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class OfficialSearchUiState(
    val query: String = "",
    val results: List<Official> = emptyList(),
    val isSearching: Boolean = false,
    val isStartingCall: Boolean = false,
    val error: String? = null
)

@OptIn(FlowPreview::class)
@HiltViewModel
class OfficialSearchViewModel @Inject constructor(
    private val officialRepository: OfficialRepository,
    private val callRepository: CallRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(OfficialSearchUiState())
    val uiState: StateFlow<OfficialSearchUiState> = _uiState.asStateFlow()

    private val _navigateToReview = MutableSharedFlow<Int>()
    val navigateToReview: SharedFlow<Int> = _navigateToReview.asSharedFlow()

    private val _launchNativeCall = MutableSharedFlow<NativeCallRequest>()
    val launchNativeCall: SharedFlow<NativeCallRequest> = _launchNativeCall.asSharedFlow()

    private val queryFlow = MutableStateFlow("")

    init {
        viewModelScope.launch {
            queryFlow.debounce(300).collectLatest { q ->
                if (q.isBlank()) {
                    _uiState.update { it.copy(results = emptyList(), isSearching = false) }
                    return@collectLatest
                }
                _uiState.update { it.copy(isSearching = true, error = null) }
                when (val result = officialRepository.search(q)) {
                    is Result.Success -> _uiState.update {
                        it.copy(isSearching = false, results = result.data)
                    }
                    is Result.Error -> _uiState.update {
                        it.copy(isSearching = false, error = result.message)
                    }
                }
            }
        }
    }

    fun onQueryChange(value: String) {
        _uiState.update { it.copy(query = value) }
        queryFlow.value = value
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
