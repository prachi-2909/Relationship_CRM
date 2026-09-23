package com.eko.rcrm.dc.data.local.db

import androidx.room.Entity
import androidx.room.PrimaryKey

object PendingUploadKind {
    const val VOICE_NOTE = "voice_note"
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
