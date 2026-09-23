package com.eko.rcrm.dc.work

import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/** Thin wrapper so ViewModels don't need to build WorkRequests by hand. */
@Singleton
class UploadScheduler @Inject constructor(
    private val workManager: WorkManager
) {
    fun enqueueUpload(pendingUploadId: Long) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val request = OneTimeWorkRequestBuilder<UploadWorker>()
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .setInputData(
                Data.Builder()
                    .putLong(UploadWorker.KEY_PENDING_UPLOAD_ID, pendingUploadId)
                    .build()
            )
            .addTag(TAG_UPLOAD)
            .build()

        workManager.enqueue(request)
    }

    companion object {
        const val TAG_UPLOAD = "rcrm_pending_upload"
    }
}
