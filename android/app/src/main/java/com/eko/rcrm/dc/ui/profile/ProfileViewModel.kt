package com.eko.rcrm.dc.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.calldetect.CallDetectionStore
import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import com.eko.rcrm.dc.data.local.CallRecordingPrefs
import com.eko.rcrm.dc.data.local.RecordingFolderStore
import dagger.hilt.android.qualifiers.ApplicationContext
import com.eko.rcrm.dc.data.repository.DcProfileRepository
import com.eko.rcrm.dc.domain.model.DcProfile
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ProfileUiState(
    val isLoading: Boolean = true,
    val profile: DcProfile? = null,
    val error: String? = null
)

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val dcProfileRepository: DcProfileRepository,
    private val callRecordingPrefs: CallRecordingPrefs,
    private val callDetectionStore: CallDetectionStore,
    private val recordingFolderStore: RecordingFolderStore,
    @ApplicationContext private val appContext: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(ProfileUiState())
    val uiState: StateFlow<ProfileUiState> = _uiState.asStateFlow()

    private val _recordCalls = MutableStateFlow(callRecordingPrefs.enabled)
    val recordCalls: StateFlow<Boolean> = _recordCalls.asStateFlow()

    /** What the auto-detector last did with a call, so the DC can see it working (or why not). */
    data class DetectionSnapshot(val message: String?, val atMs: Long)

    private val _detection = MutableStateFlow(snapshotDetection())
    val detection: StateFlow<DetectionSnapshot> = _detection.asStateFlow()

    fun refreshDetection() {
        _detection.value = snapshotDetection()
    }

    private fun snapshotDetection() =
        DetectionSnapshot(callDetectionStore.lastResult, callDetectionStore.lastResultAtMs)

    private val _recordingFolderName = MutableStateFlow(folderName())
    val recordingFolderName: StateFlow<String?> = _recordingFolderName.asStateFlow()

    private fun folderName(): String? = recordingFolderStore.treeUri?.let {
        DocumentFile.fromTreeUri(appContext, Uri.parse(it))?.name ?: "Selected folder"
    }

    fun setRecordingFolder(uri: Uri?) {
        recordingFolderStore.treeUri = uri?.toString()
        _recordingFolderName.value = folderName()
    }

    fun setRecordCalls(enabled: Boolean) {
        callRecordingPrefs.enabled = enabled
        _recordCalls.value = enabled
    }

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            when (val result = dcProfileRepository.getProfile()) {
                is Result.Success -> _uiState.update { it.copy(isLoading = false, profile = result.data) }
                is Result.Error -> _uiState.update { it.copy(isLoading = false, error = result.message) }
            }
        }
    }
}
