package com.eko.rcrm.dc.ui.home

import android.content.Context
import com.eko.rcrm.dc.BuildConfig
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.local.CallRecordingPrefs
import com.eko.rcrm.dc.data.repository.AppUpdateRepository
import com.eko.rcrm.dc.data.repository.AuthRepository
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.domain.model.AppVersionInfo
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

data class HomeUiState(
    val userName: String? = null,
    val pendingCount: Int = 0,
    val isLoading: Boolean = false,
    val error: String? = null,
    val loggedOut: Boolean = false,
    val updateAvailable: AppVersionInfo? = null,
    val isDownloadingUpdate: Boolean = false,
    val updateError: String? = null,
    val downloadedApkPath: String? = null,
    // True when the logged-in user is a Relationship Manager (they get the CSP calling list and
    // the all-call recording consent; a DC gets neither).
    val isRm: Boolean = false,
    // An RM records ALL their calls while logged in - this prompts for that consent up front
    // (shown until recording is enabled). Set false for a DC, whose recording stays CRM-gated.
    val showRmConsent: Boolean = false
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val callRepository: CallRepository,
    private val appUpdateRepository: AppUpdateRepository,
    private val callRecordingPrefs: CallRecordingPrefs,
    @ApplicationContext private val appContext: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(HomeUiState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        val cached = authRepository.cachedUserOrNull()
        _uiState.update {
            it.copy(
                userName = cached?.name,
                isRm = isRm(cached?.role),
                showRmConsent = needsRmConsent(cached?.role),
            )
        }
        loadUser()
        refresh()
        checkForUpdate()
    }

    private fun isRm(role: String?): Boolean = role.equals(ROLE_RELATIONSHIP_MANAGER, ignoreCase = true)

    /** An RM must consent to all-call recording before any call is recorded. Prompt until they
     * enable recording (consent). A DC is CRM-gated and never sees this. */
    private fun needsRmConsent(role: String?): Boolean = isRm(role) && !callRecordingPrefs.enabled

    private fun loadUser() {
        viewModelScope.launch {
            when (val result = authRepository.currentUser()) {
                is Result.Success -> _uiState.update {
                    it.copy(
                        userName = result.data.name,
                        isRm = isRm(result.data.role),
                        showRmConsent = needsRmConsent(result.data.role),
                    )
                }
                is Result.Error -> Unit // Not fatal - home still works with cached/no name.
            }
        }
    }

    /** RM agreed: enable recording (this is the consent record) and dismiss the prompt. */
    fun onRmRecordingConsent() {
        callRecordingPrefs.enabled = true
        _uiState.update { it.copy(showRmConsent = false) }
    }

    /** RM dismissed for now: recording stays OFF (no call is recorded) until they consent later. */
    fun onRmConsentDismiss() {
        _uiState.update { it.copy(showRmConsent = false) }
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

    /** Silent, best-effort - a failed version check should never block using the app. */
    private fun checkForUpdate() {
        viewModelScope.launch {
            when (val result = appUpdateRepository.checkForUpdate()) {
                is Result.Success -> {
                    val info = result.data
                    if (info.versionCode > BuildConfig.VERSION_CODE) {
                        _uiState.update { it.copy(updateAvailable = info) }
                    }
                }
                is Result.Error -> Unit
            }
        }
    }

    fun downloadUpdate() {
        val info = _uiState.value.updateAvailable ?: return
        viewModelScope.launch {
            _uiState.update { it.copy(isDownloadingUpdate = true, updateError = null) }
            val destination = File(appContext.cacheDir, "update.apk")
            when (val result = appUpdateRepository.downloadApk(info.downloadUrl, destination)) {
                is Result.Success -> _uiState.update {
                    it.copy(isDownloadingUpdate = false, downloadedApkPath = result.data.absolutePath)
                }
                is Result.Error -> _uiState.update {
                    it.copy(isDownloadingUpdate = false, updateError = result.message)
                }
            }
        }
    }

    /** Called once the caller has fired the install intent, so it isn't re-fired on recompose. */
    fun onUpdateInstallLaunched() {
        _uiState.update { it.copy(downloadedApkPath = null) }
    }

    fun onInstallPermissionMissing() {
        _uiState.update {
            it.copy(
                downloadedApkPath = null,
                updateError = "Enable install permission for this app, then tap Update again."
            )
        }
    }

    fun logout() {
        viewModelScope.launch {
            authRepository.logout()
            _uiState.update { it.copy(loggedOut = true) }
        }
    }

    private companion object {
        const val ROLE_RELATIONSHIP_MANAGER = "relationship_manager"
    }
}
