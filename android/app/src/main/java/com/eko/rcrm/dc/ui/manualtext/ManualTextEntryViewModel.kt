package com.eko.rcrm.dc.ui.manualtext

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.navigation.Routes
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ManualTextUiState(
    val text: String = "",
    val isSubmitting: Boolean = false,
    val error: String? = null,
    val saved: Boolean = false
)

/**
 * Direct suspend API call rather than the offline PendingUpload queue - manual text is small
 * and this mirrors the web app's behavior. A clear error state lets the DC retry on failure;
 * this is a deliberate, explicitly-noted simplification vs. queueing it like the voice note path.
 */
@HiltViewModel
class ManualTextEntryViewModel @Inject constructor(
    private val callRepository: CallRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    val callSessionId: Int = checkNotNull(savedStateHandle[Routes.CALL_REVIEW_ARG])

    private val _uiState = MutableStateFlow(ManualTextUiState())
    val uiState: StateFlow<ManualTextUiState> = _uiState.asStateFlow()

    fun onTextChange(value: String) {
        _uiState.update { it.copy(text = value, error = null) }
    }

    fun save() {
        val text = _uiState.value.text
        if (text.isBlank()) {
            _uiState.update { it.copy(error = "Please enter some notes before saving.") }
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(isSubmitting = true, error = null) }
            when (val result = callRepository.submitManualText(callSessionId, text)) {
                is Result.Success -> _uiState.update { it.copy(isSubmitting = false, saved = true) }
                is Result.Error -> _uiState.update { it.copy(isSubmitting = false, error = result.message) }
            }
        }
    }
}
