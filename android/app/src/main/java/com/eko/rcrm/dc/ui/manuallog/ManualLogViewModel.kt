package com.eko.rcrm.dc.ui.manuallog

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.data.repository.OfficialRepository
import com.eko.rcrm.dc.domain.model.Official
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
import java.time.Instant
import javax.inject.Inject

data class ManualLogUiState(
    val query: String = "",
    val results: List<Official> = emptyList(),
    val isSearching: Boolean = false,
    val selectedName: String? = null,
    val phone: String = "",
    val outgoing: Boolean = false,
    val durationMinutes: String = "",
    val isSubmitting: Boolean = false,
    val error: String? = null
) {
    val canSubmit: Boolean get() = phone.length >= 10 && !isSubmitting
}

/** For a call that happened on this phone outside the in-app Call button and wasn't (or can't
 * be) auto-detected - the DC picks who it was with, says which way it went and roughly how long
 * it lasted, and it lands in the Pending Queue like any other call, ready for a recap. */
@OptIn(FlowPreview::class)
@HiltViewModel
class ManualLogViewModel @Inject constructor(
    private val officialRepository: OfficialRepository,
    private val callRepository: CallRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(ManualLogUiState())
    val uiState: StateFlow<ManualLogUiState> = _uiState.asStateFlow()

    private val _navigateToReview = MutableSharedFlow<Int>()
    val navigateToReview: SharedFlow<Int> = _navigateToReview.asSharedFlow()

    private val queryFlow = MutableStateFlow("")

    init {
        viewModelScope.launch {
            queryFlow.debounce(300).collectLatest { q ->
                if (q.isBlank()) {
                    _uiState.update { it.copy(results = emptyList(), isSearching = false) }
                    return@collectLatest
                }
                _uiState.update { it.copy(isSearching = true) }
                when (val result = officialRepository.search(q)) {
                    is Result.Success -> _uiState.update { it.copy(isSearching = false, results = result.data.take(8)) }
                    is Result.Error -> _uiState.update { it.copy(isSearching = false, error = result.message) }
                }
            }
        }
    }

    fun onQueryChange(value: String) {
        _uiState.update { it.copy(query = value, error = null) }
        queryFlow.value = value
    }

    fun selectOfficial(official: Official) {
        _uiState.update {
            it.copy(
                selectedName = official.name,
                phone = official.phone?.filter { c -> c.isDigit() }.orEmpty(),
                query = "",
                results = emptyList(),
                error = if (official.phone.isNullOrBlank()) "${official.name} has no phone number saved." else null
            )
        }
        queryFlow.value = ""
    }

    fun useTypedNumber(digits: String) {
        _uiState.update { it.copy(selectedName = null, phone = digits.takeLast(15), query = "", results = emptyList()) }
        queryFlow.value = ""
    }

    fun clearSelection() {
        _uiState.update { it.copy(selectedName = null, phone = "") }
    }

    fun setOutgoing(outgoing: Boolean) {
        _uiState.update { it.copy(outgoing = outgoing) }
    }

    fun onDurationChange(value: String) {
        _uiState.update { it.copy(durationMinutes = value.filter { c -> c.isDigit() }.take(3)) }
    }

    fun submit() {
        val state = _uiState.value
        if (!state.canSubmit) return
        viewModelScope.launch {
            _uiState.update { it.copy(isSubmitting = true, error = null) }
            val seconds = (state.durationMinutes.toIntOrNull() ?: 0) * 60
            val ended = Instant.now()
            when (
                val result = callRepository.logNativeCall(
                    phone = state.phone,
                    startedAtIso = ended.minusSeconds(seconds.toLong()).toString(),
                    endedAtIso = ended.toString(),
                    durationSeconds = seconds,
                    direction = if (state.outgoing) "outbound" else "inbound",
                    manual = true
                )
            ) {
                is Result.Success -> {
                    _uiState.update { it.copy(isSubmitting = false) }
                    _navigateToReview.emit(result.data.id)
                }
                is Result.Error -> _uiState.update { it.copy(isSubmitting = false, error = result.message) }
            }
        }
    }
}
