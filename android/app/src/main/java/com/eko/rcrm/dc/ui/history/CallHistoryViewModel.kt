package com.eko.rcrm.dc.ui.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class CallHistoryUiState(
    val items: List<CallSession> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null
)

@HiltViewModel
class CallHistoryViewModel @Inject constructor(
    private val callRepository: CallRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(CallHistoryUiState())
    val uiState: StateFlow<CallHistoryUiState> = _uiState.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            when (val result = callRepository.getCallHistory()) {
                is Result.Success -> _uiState.update { it.copy(isLoading = false, items = result.data) }
                is Result.Error -> _uiState.update { it.copy(isLoading = false, error = result.message) }
            }
        }
    }
}
