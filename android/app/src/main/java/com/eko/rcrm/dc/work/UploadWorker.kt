package com.eko.rcrm.dc.work

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.eko.rcrm.dc.data.local.db.PendingUploadStatus
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.util.Result as AppResult
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

/**
 * Uploads exactly one queued voice-note or manual-text entry in the background so a DC in poor
 * network coverage is never blocked - the call log is still saved locally and will sync as soon
 * as connectivity returns. Retries via WorkManager's own exponential backoff on failure.
 *
 * Note: this class extends CoroutineWorker, whose superclass ListenableWorker declares its own
 * nested `Result` type (Success/Failure/Retry) - that inherited nested type is what "Result"
 * refers to unqualified below (WorkManager's result), while our own repository Result type is
 * imported under the alias AppResult to avoid any ambiguity between the two.
 */
@HiltWorker
class UploadWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val callRepository: CallRepository
) : CoroutineWorker(context, workerParams) {

    override suspend fun doWork(): Result {
        val uploadId = inputData.getLong(KEY_PENDING_UPLOAD_ID, -1L)
        if (uploadId == -1L) return Result.failure()

        val entity = callRepository.getPendingUpload(uploadId) ?: return Result.success()

        callRepository.markUploadStatus(entity, PendingUploadStatus.UPLOADING)

        return when (callRepository.processPendingUpload(entity)) {
            is AppResult.Success -> {
                callRepository.deletePendingUpload(entity)
                Result.success()
            }
            is AppResult.Error -> {
                if (runAttemptCount >= MAX_ATTEMPTS) {
                    callRepository.markUploadStatus(entity, PendingUploadStatus.FAILED)
                    Result.failure()
                } else {
                    callRepository.markUploadStatus(entity, PendingUploadStatus.PENDING)
                    Result.retry()
                }
            }
        }
    }

    companion object {
        const val KEY_PENDING_UPLOAD_ID = "pending_upload_id"
        private const val MAX_ATTEMPTS = 5
    }
}
