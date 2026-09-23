package com.eko.rcrm.dc.ui.review

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.data.repository.OfficialRepository
import com.eko.rcrm.dc.domain.model.CallBrief
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.navigation.Routes
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

private fun String.toCsvList(): List<String> =
    split(",").map { it.trim() }.filter { it.isNotEmpty() }

private fun List<String>.toCsv(): String = joinToString(", ")

data class CallReviewUiState(
    val isLoading: Boolean = true,
    val error: String? = null,
    val call: CallSession? = null,

    // Editable brief fields - the six list-valued fields are edited as comma-separated text,
    // mirroring the web app's editor, then split/joined on submit.
    val summary: String = "",
    val keyPointsText: String = "",
    val decisionsText: String = "",
    val commitmentsText: String = "",
    val actionItemsText: String = "",
    val opportunitiesText: String = "",
    val relationshipSignalsText: String = "",
    val suggestedNextInteraction: String = "",

    val isSubmittingAction: Boolean = false,
    val confirmed: Boolean = false,
    val remindedLater: Boolean = false,

    // Identity resolution sub-state (only relevant when call.relationshipId == null).
    val identitySearchQuery: String = "",
    val identitySearchResults: List<Official> = emptyList(),
    val isIdentitySearching: Boolean = false,
    val showCreateOfficialForm: Boolean = false
)

@HiltViewModel
class CallReviewViewModel @Inject constructor(
    private val callRepository: CallRepository,
    private val officialRepository: OfficialRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val callSessionId: Int = checkNotNull(savedStateHandle[Routes.CALL_REVIEW_ARG])

    private val _uiState = MutableStateFlow(CallReviewUiState())
    val uiState: StateFlow<CallReviewUiState> = _uiState.asStateFlow()

    init {
        loadCall()
    }

    fun loadCall() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            when (val result = callRepository.getCall(callSessionId)) {
                is Result.Success -> applyCall(result.data)
                is Result.Error -> _uiState.update { it.copy(isLoading = false, error = result.message) }
            }
        }
    }

    private fun applyCall(call: CallSession) {
        val brief = call.brief ?: CallBrief()
        _uiState.update {
            it.copy(
                isLoading = false,
                error = null,
                call = call,
                summary = brief.summary,
                keyPointsText = brief.keyPoints.toCsv(),
                decisionsText = brief.decisions.toCsv(),
                commitmentsText = brief.commitments.toCsv(),
                actionItemsText = brief.actionItems.toCsv(),
                opportunitiesText = brief.opportunities.toCsv(),
                relationshipSignalsText = brief.relationshipSignals.toCsv(),
                suggestedNextInteraction = brief.suggestedNextInteraction
            )
        }
    }

    // ---- Brief field editing ----

    fun onSummaryChange(v: String) = _uiState.update { it.copy(summary = v) }
    fun onKeyPointsChange(v: String) = _uiState.update { it.copy(keyPointsText = v) }
    fun onDecisionsChange(v: String) = _uiState.update { it.copy(decisionsText = v) }
    fun onCommitmentsChange(v: String) = _uiState.update { it.copy(commitmentsText = v) }
    fun onActionItemsChange(v: String) = _uiState.update { it.copy(actionItemsText = v) }
    fun onOpportunitiesChange(v: String) = _uiState.update { it.copy(opportunitiesText = v) }
    fun onRelationshipSignalsChange(v: String) = _uiState.update { it.copy(relationshipSignalsText = v) }
    fun onSuggestedNextInteractionChange(v: String) = _uiState.update { it.copy(suggestedNextInteraction = v) }

    private fun currentBrief(): CallBrief {
        val s = _uiState.value
        return CallBrief(
            summary = s.summary,
            keyPoints = s.keyPointsText.toCsvList(),
            decisions = s.decisionsText.toCsvList(),
            commitments = s.commitmentsText.toCsvList(),
            actionItems = s.actionItemsText.toCsvList(),
            opportunities = s.opportunitiesText.toCsvList(),
            relationshipSignals = s.relationshipSignalsText.toCsvList(),
            suggestedNextInteraction = s.suggestedNextInteraction
        )
    }

    // ---- Identity resolution ----

    /** One-click path when official_id is already known but there's no Relationship row yet. */
    fun createRelationshipWithKnownOfficial() {
        val officialId = _uiState.value.call?.officialId ?: return
        runIdentityAction { callRepository.linkIdentity(callSessionId, officialId, updatePhone = false) }
    }

    fun onIdentitySearchQueryChange(query: String) {
        _uiState.update { it.copy(identitySearchQuery = query) }
        if (query.isBlank()) {
            _uiState.update { it.copy(identitySearchResults = emptyList()) }
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(isIdentitySearching = true) }
            when (val result = officialRepository.search(query)) {
                is Result.Success -> _uiState.update {
                    it.copy(isIdentitySearching = false, identitySearchResults = result.data)
                }
                is Result.Error -> _uiState.update {
                    it.copy(isIdentitySearching = false, error = result.message)
                }
            }
        }
    }

    fun linkExistingOfficial(official: Official) {
        runIdentityAction { callRepository.linkIdentity(callSessionId, official.id, updatePhone = false) }
    }

    fun toggleCreateOfficialForm(show: Boolean) {
        _uiState.update { it.copy(showCreateOfficialForm = show) }
    }

    fun createNewOfficial(
        name: String,
        phone: String?,
        designation: String?,
        department: String?,
        level: String?,
        location: String?
    ) {
        runIdentityAction {
            callRepository.createIdentity(callSessionId, name, phone, designation, department, level, location)
        }
    }

    fun dismissIdentity() {
        runIdentityAction { callRepository.dismissIdentity(callSessionId) }
    }

    private fun runIdentityAction(block: suspend () -> Result<CallSession>) {
        viewModelScope.launch {
            _uiState.update { it.copy(isSubmittingAction = true, error = null) }
            when (val result = block()) {
                is Result.Success -> {
                    _uiState.update { it.copy(isSubmittingAction = false, showCreateOfficialForm = false) }
                    // Summary-shaped result - re-fetch full detail to keep transcript/brief in sync.
                    loadCall()
                }
                is Result.Error -> _uiState.update { it.copy(isSubmittingAction = false, error = result.message) }
            }
        }
    }

    // ---- Confirm / remind ----

    fun confirm() {
        viewModelScope.launch {
            _uiState.update { it.copy(isSubmittingAction = true, error = null) }
            when (val result = callRepository.confirmCall(callSessionId, currentBrief())) {
                is Result.Success -> _uiState.update {
                    it.copy(isSubmittingAction = false, confirmed = true, call = result.data)
                }
                is Result.Error -> _uiState.update { it.copy(isSubmittingAction = false, error = result.message) }
            }
        }
    }

    fun remindLater(hours: Int? = null) {
        viewModelScope.launch {
            _uiState.update { it.copy(isSubmittingAction = true, error = null) }
            when (val result = callRepository.remindLater(callSessionId, hours)) {
                is Result.Success -> _uiState.update { it.copy(isSubmittingAction = false, remindedLater = true) }
                is Result.Error -> _uiState.update { it.copy(isSubmittingAction = false, error = result.message) }
            }
        }
    }
}
