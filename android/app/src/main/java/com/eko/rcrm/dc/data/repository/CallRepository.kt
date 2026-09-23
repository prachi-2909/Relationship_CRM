package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.local.db.PendingUploadDao
import com.eko.rcrm.dc.data.local.db.PendingUploadEntity
import com.eko.rcrm.dc.data.local.db.PendingUploadKind
import com.eko.rcrm.dc.data.local.db.PendingUploadStatus
import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.data.remote.dto.ConfirmRequestDto
import com.eko.rcrm.dc.data.remote.dto.IdentityCreateRequestDto
import com.eko.rcrm.dc.data.remote.dto.IdentityLinkRequestDto
import com.eko.rcrm.dc.data.remote.dto.ManualTextRequestDto
import com.eko.rcrm.dc.data.remote.dto.OutgoingCallRequestDto
import com.eko.rcrm.dc.data.remote.dto.RemindLaterRequestDto
import com.eko.rcrm.dc.domain.model.CallBrief
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.util.safeApiCall
import kotlinx.coroutines.flow.Flow
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CallRepository @Inject constructor(
    private val apiService: ApiService,
    private val pendingUploadDao: PendingUploadDao
) {

    // ---- Call session lifecycle ----

    suspend fun startOutgoingCall(officialId: Int): Result<CallSession> = safeApiCall {
        apiService.startOutgoingCall(OutgoingCallRequestDto(official_id = officialId)).toDomain()
    }

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

    suspend fun uploadVoiceNoteFile(callId: Int, file: File): Result<CallSession> = safeApiCall {
        val requestBody = file.asRequestBody("audio/mp4".toMediaTypeOrNull())
        val part = MultipartBody.Part.createFormData("file", file.name, requestBody)
        apiService.uploadVoiceNote(callId, part).toDomain()
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

    suspend fun confirmCall(callId: Int, brief: CallBrief): Result<CallSession> = safeApiCall {
        apiService.confirmCall(callId, ConfirmRequestDto(brief = brief.toDto(), identity_action = "link")).toDomain()
    }

    suspend fun remindLater(callId: Int, hours: Int?): Result<CallSession> = safeApiCall {
        apiService.remindLater(callId, RemindLaterRequestDto(hours = hours)).toDomain()
    }

    // ---- Offline-resilient upload queue (backs UploadWorker) ----

    fun observePendingUploads(): Flow<List<PendingUploadEntity>> = pendingUploadDao.observeAll()

    suspend fun enqueueVoiceNoteUpload(callSessionId: Int, localFilePath: String): Long =
        pendingUploadDao.insert(
            PendingUploadEntity(
                callSessionId = callSessionId,
                kind = PendingUploadKind.VOICE_NOTE,
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

    /** Processes exactly one queued upload; used by both UploadWorker and any immediate-attempt path. */
    suspend fun processPendingUpload(entity: PendingUploadEntity): Result<CallSession> {
        return when (entity.kind) {
            PendingUploadKind.VOICE_NOTE -> {
                val path = entity.localFilePath
                if (path.isNullOrBlank()) {
                    Result.Error("Voice note file path missing")
                } else {
                    uploadVoiceNoteFile(entity.callSessionId, File(path))
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
