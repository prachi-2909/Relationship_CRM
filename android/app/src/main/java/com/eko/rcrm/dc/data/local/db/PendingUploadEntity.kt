package com.eko.rcrm.dc.data.local.db

import androidx.room.Entity
import androidx.room.PrimaryKey

/** VOICE_NOTE and CALL_RECORDING double as the `kind` sent to POST calls/{id}/voice-note: the
 * server accepts a CALL_RECORDING only for a CRM official's number. */
object PendingUploadKind {
    const val VOICE_NOTE = "voice_note"
    const val CALL_RECORDING = "call_recording"
    const val MANUAL_TEXT = "manual_text"
}

object PendingUploadStatus {
    const val PENDING = "pending"
    const val UPLOADING = "uploading"
    const val FAILED = "failed"
}

@Entity(tableName = "pending_uploads")
data class PendingUploadEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val callSessionId: Int,
    val kind: String,
    val localFilePath: String? = null,
    val textContent: String? = null,
    val createdAt: Long,
    val status: String
)
