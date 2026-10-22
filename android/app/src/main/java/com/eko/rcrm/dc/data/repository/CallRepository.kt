package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.BuildConfig
import com.eko.rcrm.dc.data.local.CallAudioStore
import com.eko.rcrm.dc.data.local.db.ArmedNativeCallDao
import com.eko.rcrm.dc.data.local.db.ArmedNativeCallEntity
import com.eko.rcrm.dc.data.local.db.ArmedNativeCallState
import com.eko.rcrm.dc.data.local.db.PendingUploadDao
import com.eko.rcrm.dc.data.local.db.PendingUploadEntity
import com.eko.rcrm.dc.data.local.db.PendingUploadKind
import com.eko.rcrm.dc.data.local.db.PendingUploadStatus
import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.data.remote.dto.CallerLookupRequestDto
import com.eko.rcrm.dc.data.remote.dto.ConfirmRequestDto
import com.eko.rcrm.dc.data.remote.dto.IdentityCreateRequestDto
import com.eko.rcrm.dc.data.remote.dto.IncomingNativeCallRequestDto
import com.eko.rcrm.dc.data.remote.dto.IdentityLinkRequestDto
import com.eko.rcrm.dc.data.remote.dto.ManualTextRequestDto
import com.eko.rcrm.dc.data.remote.dto.NativeCallCompleteRequestDto
import com.eko.rcrm.dc.data.remote.dto.OutgoingCallRequestDto
import com.eko.rcrm.dc.data.remote.dto.RemindLaterRequestDto
import com.eko.rcrm.dc.domain.model.CallBrief
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.util.safeApiCall
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.HttpException
import java.io.File
import java.io.FileOutputStream
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CallRepository @Inject constructor(
    private val apiService: ApiService,
    private val pendingUploadDao: PendingUploadDao,
    private val armedNativeCallDao: ArmedNativeCallDao,
    private val okHttpClient: OkHttpClient,
    private val callAudioStore: CallAudioStore
) {

    // ---- Call session lifecycle ----

    suspend fun startOutgoingCall(officialId: Int): Result<CallSession> = safeApiCall {
        apiService.startOutgoingCall(OutgoingCallRequestDto(official_id = officialId)).toDomain()
    }

    /** In-app dial pad: a manually typed number with no matching official record. */
    suspend fun startManualCall(phone: String): Result<CallSession> = safeApiCall {
        apiService.startOutgoingCall(OutgoingCallRequestDto(phone = phone)).toDomain()
    }

    // ---- Android-native (SIM) calling ----

    /** Reports what happened after this device placed a native-SIM call itself - see
     * services/call_intelligence.py::complete_native_call on the backend. */
    suspend fun completeNativeCall(
        callId: Int,
        endedAtIso: String,
        durationSeconds: Int,
        connected: Boolean,
        recordingEngineId: String? = null,
        recordingCapabilityLevel: String? = null
    ): Result<CallSession> = safeApiCall {
        apiService.completeNativeCall(
            callId,
            NativeCallCompleteRequestDto(
                ended_at = endedAtIso,
                duration_seconds = durationSeconds,
                connected = connected,
                recording_engine = recordingEngineId,
                recording_capability_status = recordingCapabilityLevel
            )
        ).toDomain()
    }

    /** Reports a call made or received on this phone outside the in-app Call button. The
     * backend ignores a duplicate of a call it already has, so retrying is always safe. */
    suspend fun logNativeCall(
        phone: String,
        startedAtIso: String,
        endedAtIso: String,
        durationSeconds: Int,
        direction: String,
        manual: Boolean
    ): Result<CallSession> = safeApiCall {
        apiService.logNativeCall(
            IncomingNativeCallRequestDto(
                phone = phone,
                started_at = startedAtIso,
                ended_at = endedAtIso,
                duration_seconds = durationSeconds,
                direction = direction,
                manual = manual
            )
        ).toDomain()
    }

    /** The CRM official (in this DC's territory) behind a phone number, or null for no match. */
    suspend fun lookupCaller(phone: String): Result<String?> = safeApiCall {
        apiService.lookupCaller(CallerLookupRequestDto(phone)).official?.name
    }

    /** Whether this call may be recorded per the server: either [phone] is an active CRM official in
     * the DC's territory, OR the logged-in user is a Relationship Manager (record_all=true), who
     * records every call. Mirrors assert_call_recording_allowed on the server. */
    suspend fun isCrmContact(phone: String): Result<Boolean> = safeApiCall {
        val resp = apiService.lookupCaller(CallerLookupRequestDto(phone))
        resp.official != null || resp.record_all
    }

    /** Single-flight: at most one native call is ever in flight. Callers should check
     * [hasActiveArmedNativeCall] first and refuse to start a new call while one is armed. */
    suspend fun armNativeCall(callSessionId: Int, phone: String) {
        armedNativeCallDao.arm(
            ArmedNativeCallEntity(
                callSessionId = callSessionId,
                phone = phone,
                armedAtEpochMs = System.currentTimeMillis(),
                state = ArmedNativeCallState.ARMED
            )
        )
    }

    suspend fun currentArmedNativeCall(): ArmedNativeCallEntity? = armedNativeCallDao.current()

    /** A row this old can only be an orphan - NativeCallForegroundService failing to report
     * back (a crash, a platform restriction, the process getting killed) must never
     * permanently brick the Call button, so a stale row is cleared and treated as "nothing
     * in flight" rather than blocking the DC forever. Two different staleness windows:
     * a row still stuck at ARMED never even got a confirmed OFFHOOK from the service, which
     * under normal operation happens within seconds of dialing - if it hasn't after
     * [ARMED_STALE_MS], the service almost certainly never ran or died immediately, so this
     * clears fast. A row that reached IN_PROGRESS is a real, observed, still-ongoing call,
     * so it gets the much longer [IN_PROGRESS_STALE_MS] - long enough for any real call,
     * short enough to still self-heal if that call's completion report never arrives. */
    suspend fun hasActiveArmedNativeCall(): Boolean {
        val armed = armedNativeCallDao.current() ?: return false
        val age = System.currentTimeMillis() - armed.armedAtEpochMs
        val staleAfter = if (armed.state == ArmedNativeCallState.IN_PROGRESS) IN_PROGRESS_STALE_MS else ARMED_STALE_MS
        if (age > staleAfter) {
            armedNativeCallDao.clear()
            return false
        }
        return true
    }

    suspend fun markArmedNativeCallInProgress(callSessionId: Int) {
        armedNativeCallDao.updateState(callSessionId, ArmedNativeCallState.IN_PROGRESS)
    }

    companion object {
        private const val ARMED_STALE_MS = 60 * 1000L
        private const val IN_PROGRESS_STALE_MS = 10 * 60 * 1000L
        private val PERMANENT_REJECTION_CODES = setOf(403, 404, 413, 422)
    }

    suspend fun clearArmedNativeCall() = armedNativeCallDao.clear()

    suspend fun getPendingCalls(): Result<List<CallSession>> = safeApiCall {
        apiService.getPendingCalls().items.map { it.toDomain() }
    }

    suspend fun getCallHistory(): Result<List<CallSession>> = safeApiCall {
        apiService.getCallHistory().items.map { it.toDomain() }
    }

    suspend fun getCall(id: Int): Result<CallSession> = safeApiCall {
        apiService.getCall(id).toDomain()
    }

    // ---- Recording-fail-safe fallback paths ----

    suspend fun submitManualText(callId: Int, text: String): Result<CallSession> = safeApiCall {
        apiService.submitManualText(callId, ManualTextRequestDto(text = text)).toDomain()
    }

    /** Uploads [file] as [kind] (PendingUploadKind.VOICE_NOTE or CALL_RECORDING) and then deletes
     * it from the phone - the server's copy is the only one needed from here on. Also deleted when
     * the server refuses it for good (e.g. a call recording for a number not in the CRM), since no
     * retry could ever succeed. Kept only for a retryable failure (no network, server error). */
    suspend fun uploadVoiceNoteFile(
        callId: Int,
        file: File,
        kind: String = PendingUploadKind.VOICE_NOTE
    ): Result<CallSession> {
        val result = safeApiCall {
            val requestBody = file.asRequestBody("audio/mp4".toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("file", file.name, requestBody)
            apiService.uploadVoiceNote(callId, part, kind.toRequestBody("text/plain".toMediaTypeOrNull())).toDomain()
        }
        if (result is Result.Success || isPermanentRejection(result)) file.delete()
        return result
    }

    /** A 4xx the same request can never get past - unlike 401 (re-login), 408 or 429. */
    fun isPermanentRejection(result: Result<*>): Boolean {
        val code = ((result as? Result.Error)?.throwable as? HttpException)?.code() ?: return false
        return code in PERMANENT_REJECTION_CODES
    }

    /** Downloads the call's voice note into [destination] so it can be played locally with
     * MediaPlayer - simpler and more robust than streaming with manually attached auth headers. */
    suspend fun downloadVoiceNoteAudio(callId: Int, destination: File): Result<File> = safeApiCall {
        withContext(Dispatchers.IO) {
            val url = BuildConfig.API_BASE_URL + "calls/$callId/voice-note/audio"
            val request = Request.Builder().url(url).get().build()
            okHttpClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    error("Download failed: HTTP ${response.code}")
                }
                val body = response.body ?: error("Empty voice note response")
                body.byteStream().use { input ->
                    FileOutputStream(destination).use { output -> input.copyTo(output) }
                }
            }
            destination
        }
    }

    suspend fun discardVoiceNote(callId: Int): Result<CallSession> = safeApiCall {
        apiService.deleteVoiceNote(callId).toDomain()
    }

    // ---- Identity resolution ----

    suspend fun linkIdentity(
        callId: Int,
        officialId: Int,
        updatePhone: Boolean = false
    ): Result<CallSession> = safeApiCall {
        apiService.linkIdentity(callId, IdentityLinkRequestDto(officialId, updatePhone)).toDomain()
    }

    suspend fun createIdentity(
        callId: Int,
        name: String,
        phone: String?,
        designation: String?,
        department: String?,
        level: String?,
        location: String?
    ): Result<CallSession> = safeApiCall {
        apiService.createIdentity(
            callId,
            IdentityCreateRequestDto(name, phone, designation, department, level, location)
        ).toDomain()
    }

    suspend fun dismissIdentity(callId: Int): Result<CallSession> = safeApiCall {
        apiService.dismissIdentity(callId).toDomain()
    }

    // ---- Confirm / remind ----

    /** Logs the call into the CRM. Once logged, no audio of it may remain on the phone (the server
     * deletes its own copy in the same step): local files, the review playback copy and any audio
     * still queued for upload are all deleted. */
    suspend fun confirmCall(callId: Int, brief: CallBrief): Result<CallSession> {
        val result = safeApiCall {
            apiService.confirmCall(callId, ConfirmRequestDto(brief = brief.toDto(), identity_action = "link")).toDomain()
        }
        if (result is Result.Success) purgeLocalAudio(callId)
        return result
    }

    suspend fun purgeLocalAudio(callId: Int) {
        pendingUploadDao.deleteAudioForCall(callId)
        callAudioStore.purgeCall(callId)
    }

    suspend fun remindLater(callId: Int, hours: Int?): Result<CallSession> = safeApiCall {
        apiService.remindLater(callId, RemindLaterRequestDto(hours = hours)).toDomain()
    }

    // ---- Offline-resilient upload queue (backs UploadWorker) ----

    fun observePendingUploads(): Flow<List<PendingUploadEntity>> = pendingUploadDao.observeAll()

    suspend fun enqueueVoiceNoteUpload(
        callSessionId: Int,
        localFilePath: String,
        kind: String = PendingUploadKind.VOICE_NOTE
    ): Long =
        pendingUploadDao.insert(
            PendingUploadEntity(
                callSessionId = callSessionId,
                kind = kind,
                localFilePath = localFilePath,
                textContent = null,
                createdAt = System.currentTimeMillis(),
                status = PendingUploadStatus.PENDING
            )
        )

    suspend fun enqueueManualTextUpload(callSessionId: Int, text: String): Long =
        pendingUploadDao.insert(
            PendingUploadEntity(
                callSessionId = callSessionId,
                kind = PendingUploadKind.MANUAL_TEXT,
                localFilePath = null,
                textContent = text,
                createdAt = System.currentTimeMillis(),
                status = PendingUploadStatus.PENDING
            )
        )

    suspend fun getPendingUpload(id: Long): PendingUploadEntity? = pendingUploadDao.getById(id)

    suspend fun getAllPendingUploads(): List<PendingUploadEntity> = pendingUploadDao.getAllPending()

    suspend fun markUploadStatus(entity: PendingUploadEntity, status: String) {
        pendingUploadDao.update(entity.copy(status = status))
    }

    suspend fun deletePendingUpload(entity: PendingUploadEntity) {
        pendingUploadDao.delete(entity)
    }

    /** Gives up on a queued upload for good: the row and, for audio, the file itself. */
    suspend fun abandonPendingUpload(entity: PendingUploadEntity) {
        entity.localFilePath?.let { File(it).delete() }
        pendingUploadDao.delete(entity)
    }

    /** Processes exactly one queued upload; used by both UploadWorker and any immediate-attempt path. */
    suspend fun processPendingUpload(entity: PendingUploadEntity): Result<CallSession> {
        return when (entity.kind) {
            PendingUploadKind.VOICE_NOTE, PendingUploadKind.CALL_RECORDING -> {
                val path = entity.localFilePath
                if (path.isNullOrBlank()) {
                    Result.Error("Voice note file path missing")
                } else {
                    uploadVoiceNoteFile(entity.callSessionId, File(path), entity.kind)
                }
            }
            PendingUploadKind.MANUAL_TEXT -> {
                val text = entity.textContent
                if (text.isNullOrBlank()) {
                    Result.Error("Manual text content missing")
                } else {
                    submitManualText(entity.callSessionId, text)
                }
            }
            else -> Result.Error("Unknown pending upload kind: ${entity.kind}")
        }
    }
}
