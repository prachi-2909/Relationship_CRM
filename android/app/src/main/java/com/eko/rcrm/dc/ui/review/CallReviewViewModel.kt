package com.eko.rcrm.dc.ui.review

import android.content.Context
import android.media.MediaPlayer
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import android.net.Uri
import com.eko.rcrm.dc.data.local.RecordingFolderStore
import com.eko.rcrm.dc.data.recording.RecordingImporter
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.data.repository.OfficialRepository
import com.eko.rcrm.dc.domain.model.CallBrief
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.navigation.Routes
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
    val showCreateOfficialForm: Boolean = false,

    // Voice note playback/discard - only relevant when call.hasVoiceNote is true.
    val isLoadingVoiceNoteAudio: Boolean = false,
    val isPlayingVoiceNoteAudio: Boolean = false,
    val isDiscardingVoiceNote: Boolean = false,
    // Player position/length (ms) for the scrubber + timer. prepared flips true once the audio is
    // loaded, so the bar shows even while paused.
    val voiceNotePrepared: Boolean = false,
    val playbackPositionMs: Int = 0,
    val playbackDurationMs: Int = 0,

    // Attaching a recording made by a separate call-recorder app.
    val isAttachingRecording: Boolean = false,
    val recordingNote: String? = null,
    val hasRecordingFolder: Boolean = false
)

@HiltViewModel
class CallReviewViewModel @Inject constructor(
    private val callRepository: CallRepository,
    private val officialRepository: OfficialRepository,
    private val recordingImporter: RecordingImporter,
    private val recordingFolderStore: RecordingFolderStore,
    @ApplicationContext private val appContext: Context,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val callSessionId: Int = checkNotNull(savedStateHandle[Routes.CALL_REVIEW_ARG])

    private val _uiState = MutableStateFlow(CallReviewUiState())
    val uiState: StateFlow<CallReviewUiState> = _uiState.asStateFlow()

    private var mediaPlayer: MediaPlayer? = null
    private var autoAttachTried = false

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
                suggestedNextInteraction = brief.suggestedNextInteraction,
                hasRecordingFolder = recordingFolderStore.treeUri != null
            )
        }
        maybeAutoAttachRecording(call)
    }

    // ---- Recording from a separate call-recorder app ----

    /** Once per screen visit, if the DC has chosen a recordings folder, look there for this call's recording. */
    private fun maybeAutoAttachRecording(call: CallSession) {
        if (autoAttachTried || !call.canAttachRecording || recordingFolderStore.treeUri == null) return
        autoAttachTried = true
        attachRecordingFromFolder()
    }

    fun attachRecordingFromFolder() {
        val call = _uiState.value.call ?: return
        runRecordingAttach { recordingImporter.attachFromFolder(call) }
    }

    fun attachPickedRecording(uri: Uri, displayName: String?) {
        val call = _uiState.value.call ?: return
        runRecordingAttach { recordingImporter.attachPicked(call, uri, displayName) }
    }

    private fun runRecordingAttach(block: suspend () -> RecordingImporter.Outcome) {
        if (_uiState.value.isAttachingRecording) return
        viewModelScope.launch {
            _uiState.update { it.copy(isAttachingRecording = true, recordingNote = null) }
            when (val outcome = block()) {
                is RecordingImporter.Outcome.Attached -> {
                    applyCall(outcome.call)
                    _uiState.update { it.copy(isAttachingRecording = false, recordingNote = "Recording attached and transcribed.") }
                }
                RecordingImporter.Outcome.NotFound -> _uiState.update {
                    it.copy(isAttachingRecording = false, recordingNote = "No matching recording found in the folder yet. Your recorder may still be saving it - try again in a moment.")
                }
                RecordingImporter.Outcome.NoFolder -> _uiState.update {
                    it.copy(isAttachingRecording = false, recordingNote = "Choose your call recordings folder in Profile first.")
                }
                is RecordingImporter.Outcome.Failed -> _uiState.update {
                    it.copy(isAttachingRecording = false, recordingNote = outcome.message)
                }
            }
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

    // ---- Voice note playback / discard ----

    private fun localVoiceNoteFile(): File = File(appContext.cacheDir, "voice_note_review_$callSessionId.m4a")

    private var playbackTicker: kotlinx.coroutines.Job? = null

    /** Play or resume. Downloads the recording once per visit, prepares the player (so the scrubber
     * and length show), then starts playback and the position ticker. */
    fun playVoiceNote() {
        if (_uiState.value.isPlayingVoiceNoteAudio || _uiState.value.isLoadingVoiceNoteAudio) return
        // Already prepared (e.g. paused) - just resume from the current position.
        val existing = mediaPlayer
        if (existing != null && _uiState.value.voiceNotePrepared) {
            existing.start()
            _uiState.update { it.copy(isPlayingVoiceNoteAudio = true) }
            startTicker()
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(isLoadingVoiceNoteAudio = true, error = null) }
            val destination = localVoiceNoteFile()
            val ready = if (destination.exists() && destination.length() > 0) {
                Result.Success(destination)
            } else {
                callRepository.downloadVoiceNoteAudio(callSessionId, destination)
            }
            when (ready) {
                is Result.Success -> startPlayback(ready.data)
                is Result.Error -> _uiState.update {
                    it.copy(isLoadingVoiceNoteAudio = false, error = ready.message)
                }
            }
        }
    }

    private fun startPlayback(file: File) {
        stopPlaybackInternal()
        try {
            mediaPlayer = MediaPlayer().apply {
                setDataSource(file.absolutePath)
                setOnCompletionListener {
                    playbackTicker?.cancel()
                    _uiState.update { it.copy(isPlayingVoiceNoteAudio = false, playbackPositionMs = 0) }
                    runCatching { seekTo(0) }
                }
                setOnErrorListener { _, _, _ ->
                    _uiState.update { it.copy(isPlayingVoiceNoteAudio = false, error = "Could not play the recording") }
                    true
                }
                prepare()
                start()
            }
            _uiState.update {
                it.copy(
                    isLoadingVoiceNoteAudio = false,
                    isPlayingVoiceNoteAudio = true,
                    voiceNotePrepared = true,
                    playbackDurationMs = mediaPlayer?.duration?.coerceAtLeast(0) ?: 0,
                    playbackPositionMs = 0,
                )
            }
            startTicker()
        } catch (e: Exception) {
            _uiState.update { it.copy(isLoadingVoiceNoteAudio = false, error = "Could not play the recording") }
        }
    }

    /** Pause without tearing down, so Play resumes from the same spot. */
    fun pauseVoiceNote() {
        playbackTicker?.cancel()
        runCatching { mediaPlayer?.takeIf { it.isPlaying }?.pause() }
        _uiState.update { it.copy(isPlayingVoiceNoteAudio = false) }
    }

    /** Jump to [ms] - the draggable bar / forward-back. */
    fun seekTo(ms: Int) {
        val mp = mediaPlayer ?: return
        val clamped = ms.coerceIn(0, _uiState.value.playbackDurationMs)
        runCatching { mp.seekTo(clamped) }
        _uiState.update { it.copy(playbackPositionMs = clamped) }
    }

    private fun startTicker() {
        playbackTicker?.cancel()
        playbackTicker = viewModelScope.launch {
            while (true) {
                val mp = mediaPlayer ?: break
                val pos = runCatching { mp.currentPosition }.getOrDefault(0)
                _uiState.update { it.copy(playbackPositionMs = pos) }
                kotlinx.coroutines.delay(200)
            }
        }
    }

    fun stopVoiceNotePlayback() {
        stopPlaybackInternal()
        _uiState.update { it.copy(isPlayingVoiceNoteAudio = false, voiceNotePrepared = false, playbackPositionMs = 0, playbackDurationMs = 0) }
    }

    private fun stopPlaybackInternal() {
        playbackTicker?.cancel()
        playbackTicker = null
        mediaPlayer?.apply {
            if (isPlaying) stop()
            release()
        }
        mediaPlayer = null
    }

    fun discardVoiceNote() {
        stopPlaybackInternal()
        localVoiceNoteFile().delete()
        viewModelScope.launch {
            _uiState.update { it.copy(isDiscardingVoiceNote = true, isPlayingVoiceNoteAudio = false, error = null) }
            when (val result = callRepository.discardVoiceNote(callSessionId)) {
                is Result.Success -> {
                    applyCall(result.data)
                    _uiState.update { it.copy(isDiscardingVoiceNote = false) }
                }
                is Result.Error -> _uiState.update { it.copy(isDiscardingVoiceNote = false, error = result.message) }
            }
        }
    }

    override fun onCleared() {
        stopPlaybackInternal()
        // The playback copy is re-downloaded on the next visit; never leave it behind on the phone.
        localVoiceNoteFile().delete()
        super.onCleared()
    }
}
