package com.eko.rcrm.dc.ui.voicenote

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.navigation.Routes
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.work.UploadScheduler
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import java.util.Locale
import javax.inject.Inject

enum class VoiceNoteStage { IDLE, RECORDING, RECORDED, UPLOADING, UPLOADED_DIRECT, QUEUED_OFFLINE }

data class VoiceNoteUiState(
    val stage: VoiceNoteStage = VoiceNoteStage.IDLE,
    val elapsedSeconds: Int = 0,
    val error: String? = null
)

@HiltViewModel
class VoiceNoteRecordingViewModel @Inject constructor(
    @ApplicationContext private val appContext: Context,
    private val callRepository: CallRepository,
    private val uploadScheduler: UploadScheduler,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    val callSessionId: Int = checkNotNull(savedStateHandle[Routes.CALL_REVIEW_ARG])

    private val _uiState = MutableStateFlow(VoiceNoteUiState())
    val uiState: StateFlow<VoiceNoteUiState> = _uiState.asStateFlow()

    private var recorder: MediaRecorder? = null
    private var outputFile: File? = null
    private var timerJob: kotlinx.coroutines.Job? = null

    fun startRecording() {
        if (_uiState.value.stage == VoiceNoteStage.RECORDING) return
        try {
            val dir = File(appContext.filesDir, "voice_notes").apply { mkdirs() }
            val fileName = "voicenote_${callSessionId}_${System.currentTimeMillis()}.m4a"
            val file = File(dir, fileName)
            outputFile = file

            @Suppress("DEPRECATION")
            val mediaRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(appContext)
            } else {
                MediaRecorder()
            }
            mediaRecorder.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioEncodingBitRate(96000)
                setAudioSamplingRate(44100)
                setOutputFile(file.absolutePath)
                prepare()
                start()
            }
            recorder = mediaRecorder
            _uiState.update { it.copy(stage = VoiceNoteStage.RECORDING, elapsedSeconds = 0, error = null) }
            startTimer()
        } catch (t: Throwable) {
            _uiState.update { it.copy(error = "Could not start recording: ${t.message}") }
            releaseRecorder()
        }
    }

    fun stopRecording() {
        if (_uiState.value.stage != VoiceNoteStage.RECORDING) return
        stopTimer()
        try {
            recorder?.apply {
                stop()
                release()
            }
        } catch (_: Throwable) {
            // stop() can throw if too little was recorded - the file may still be unusable,
            // the DC can just discard and retry, or fall back to manual text entirely.
        }
        recorder = null
        _uiState.update { it.copy(stage = VoiceNoteStage.RECORDED) }
    }

    fun discardRecording() {
        stopTimer()
        releaseRecorder()
        outputFile?.delete()
        outputFile = null
        _uiState.update { VoiceNoteUiState() }
    }

    /** Attempts an immediate upload; falls back to the offline queue (WorkManager) if it fails. */
    fun saveAndUpload() {
        val file = outputFile ?: run {
            _uiState.update { it.copy(error = "No recording to save.") }
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(stage = VoiceNoteStage.UPLOADING, error = null) }
            when (val result = callRepository.uploadVoiceNoteFile(callSessionId, file)) {
                is Result.Success -> _uiState.update { it.copy(stage = VoiceNoteStage.UPLOADED_DIRECT) }
                is Result.Error -> {
                    // Offline / flaky network - queue for WorkManager instead of blocking the DC.
                    val uploadId = callRepository.enqueueVoiceNoteUpload(callSessionId, file.absolutePath)
                    uploadScheduler.enqueueUpload(uploadId)
                    _uiState.update { it.copy(stage = VoiceNoteStage.QUEUED_OFFLINE) }
                }
            }
        }
    }

    private fun startTimer() {
        timerJob = viewModelScope.launch {
            while (true) {
                kotlinx.coroutines.delay(1000)
                _uiState.update { it.copy(elapsedSeconds = it.elapsedSeconds + 1) }
            }
        }
    }

    private fun stopTimer() {
        timerJob?.cancel()
        timerJob = null
    }

    private fun releaseRecorder() {
        try {
            recorder?.release()
        } catch (_: Throwable) {
        }
        recorder = null
    }

    override fun onCleared() {
        super.onCleared()
        stopTimer()
        releaseRecorder()
    }

    companion object {
        fun formatElapsed(seconds: Int): String =
            String.format(Locale.US, "%02d:%02d", seconds / 60, seconds % 60)
    }
}
