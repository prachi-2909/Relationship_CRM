package com.eko.rcrm.dc.ui.officialedit

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.DcProfileRepository
import com.eko.rcrm.dc.data.repository.OfficialRepository
import com.eko.rcrm.dc.domain.model.DcTerritory
import com.eko.rcrm.dc.navigation.Routes
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class OfficialEditUiState(
    val isEdit: Boolean = false,
    val isLoadingInitial: Boolean = true,
    val name: String = "",
    val phone: String = "",
    val email: String = "",
    val designation: String = "",
    val department: String = "",
    val level: String = "",
    val location: String = "",
    val territories: List<DcTerritory> = emptyList(),
    val selectedOrganizationUnitId: Int? = null,
    val isSubmitting: Boolean = false,
    val error: String? = null,
    val saved: Boolean = false
)

/**
 * Shared by create and edit - a null/[NO_OFFICIAL_ID] officialId means "create new". The
 * org-unit picker only offers the DC's own directly-assigned territory units (from
 * dc-territories); browsing descendant/sub-units is deliberately out of scope for v1 - picking
 * one of the DC's own units is always a valid, server-accepted choice.
 */
@HiltViewModel
class OfficialEditViewModel @Inject constructor(
    private val officialRepository: OfficialRepository,
    private val dcProfileRepository: DcProfileRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val officialId: Int? =
        (savedStateHandle.get<Int>(Routes.OFFICIAL_EDIT_ARG) ?: NO_OFFICIAL_ID)
            .takeIf { it != NO_OFFICIAL_ID }

    private val _uiState = MutableStateFlow(OfficialEditUiState(isEdit = officialId != null))
    val uiState: StateFlow<OfficialEditUiState> = _uiState.asStateFlow()

    init {
        loadTerritories()
        val id = officialId
        if (id != null) {
            loadOfficial(id)
        } else {
            _uiState.update { it.copy(isLoadingInitial = false) }
        }
    }

    private fun loadTerritories() {
        viewModelScope.launch {
            when (val result = dcProfileRepository.getTerritories()) {
                is Result.Success -> _uiState.update { state ->
                    state.copy(
                        territories = result.data,
                        selectedOrganizationUnitId = state.selectedOrganizationUnitId
                            ?: result.data.firstOrNull()?.organizationUnitId
                    )
                }
                is Result.Error -> _uiState.update { it.copy(error = result.message) }
            }
        }
    }

    private fun loadOfficial(id: Int) {
        viewModelScope.launch {
            when (val result = officialRepository.getOfficial(id)) {
                is Result.Success -> {
                    val official = result.data
                    _uiState.update {
                        it.copy(
                            isLoadingInitial = false,
                            name = official.name,
                            phone = official.phone.orEmpty(),
                            email = official.email.orEmpty(),
                            designation = official.designation.orEmpty(),
                            department = official.department.orEmpty(),
                            level = official.level.orEmpty(),
                            location = official.location.orEmpty(),
                            selectedOrganizationUnitId = official.organizationUnitId ?: it.selectedOrganizationUnitId
                        )
                    }
                }
                is Result.Error -> _uiState.update { it.copy(isLoadingInitial = false, error = result.message) }
            }
        }
    }

    fun onNameChange(value: String) = _uiState.update { it.copy(name = value, error = null) }
    fun onPhoneChange(value: String) = _uiState.update { it.copy(phone = value) }
    fun onEmailChange(value: String) = _uiState.update { it.copy(email = value) }
    fun onDesignationChange(value: String) = _uiState.update { it.copy(designation = value) }
    fun onDepartmentChange(value: String) = _uiState.update { it.copy(department = value) }
    fun onLevelChange(value: String) = _uiState.update { it.copy(level = value) }
    fun onLocationChange(value: String) = _uiState.update { it.copy(location = value) }
    fun onOrganizationUnitSelected(id: Int) = _uiState.update { it.copy(selectedOrganizationUnitId = id) }

    fun submit() {
        val state = _uiState.value
        if (state.name.isBlank()) {
            _uiState.update { it.copy(error = "Name is required.") }
            return
        }
        val organizationUnitId = state.selectedOrganizationUnitId
        if (organizationUnitId == null) {
            _uiState.update { it.copy(error = "Please select a territory unit.") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isSubmitting = true, error = null) }
            val result = if (officialId == null) {
                officialRepository.createOfficial(
                    name = state.name.trim(),
                    phone = state.phone.trim().ifBlank { null },
                    email = state.email.trim().ifBlank { null },
                    designation = state.designation.trim().ifBlank { null },
                    department = state.department.trim().ifBlank { null },
                    level = state.level.trim().ifBlank { null },
                    location = state.location.trim().ifBlank { null },
                    organizationUnitId = organizationUnitId
                )
            } else {
                officialRepository.updateOfficial(
                    id = officialId,
                    name = state.name.trim(),
                    phone = state.phone.trim().ifBlank { null },
                    email = state.email.trim().ifBlank { null },
                    designation = state.designation.trim().ifBlank { null },
                    department = state.department.trim().ifBlank { null },
                    level = state.level.trim().ifBlank { null },
                    location = state.location.trim().ifBlank { null },
                    organizationUnitId = organizationUnitId
                )
            }
            when (result) {
                is Result.Success -> _uiState.update { it.copy(isSubmitting = false, saved = true) }
                is Result.Error -> _uiState.update { it.copy(isSubmitting = false, error = result.message) }
            }
        }
    }

    companion object {
        const val NO_OFFICIAL_ID = -1
    }
}
