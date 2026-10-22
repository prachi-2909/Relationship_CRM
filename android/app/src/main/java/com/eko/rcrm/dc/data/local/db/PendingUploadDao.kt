package com.eko.rcrm.dc.data.local.db

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface PendingUploadDao {

    @Insert
    suspend fun insert(entity: PendingUploadEntity): Long

    @Update
    suspend fun update(entity: PendingUploadEntity)

    @Delete
    suspend fun delete(entity: PendingUploadEntity)

    @Query("SELECT * FROM pending_uploads WHERE id = :id LIMIT 1")
    suspend fun getById(id: Long): PendingUploadEntity?

    @Query("SELECT * FROM pending_uploads ORDER BY createdAt ASC")
    fun observeAll(): Flow<List<PendingUploadEntity>>

    @Query("SELECT * FROM pending_uploads WHERE status != 'uploading' ORDER BY createdAt ASC")
    suspend fun getAllPending(): List<PendingUploadEntity>

    /** Queued audio for a call - once the call is logged it must never be uploaded. */
    @Query("DELETE FROM pending_uploads WHERE callSessionId = :callSessionId AND localFilePath IS NOT NULL")
    suspend fun deleteAudioForCall(callSessionId: Int)
}
