package com.eko.rcrm.dc.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.AuthRepository
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class HomeUiState(
    val userName: String? = null,
    val pendingCount: Int = 0,
    val isLoading: Boolean = false,
    val error: String? = null,
    val loggedOut: Boolean = false
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val callRepository: CallRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(HomeUiState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        _uiState.update { it.copy(userName = authRepository.cachedUserOrNull()?.name) }
        loadUser()
        refresh()
    }

    private fun loadUser() {
        viewModelScope.launch {
            when (val result = authRepository.currentUser()) {
                is Result.Success -> _uiState.update { it.copy(userName = result.data.name) }
                is Result.Error -> Unit // Not fatal - home still works with cached/no name.
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            when (val result = callRepository.getPendingCalls()) {
                is Result.Success -> _uiState.update {
                    it.copy(isLoading = false, pendingCount = result.data.size)
                }
                is Result.Error -> _uiState.update {
                    it.copy(isLoading = false, error = result.message)
                }
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            authRepository.logout()
            _uiState.update { it.copy(loggedOut = true) }
        }
    }
}
