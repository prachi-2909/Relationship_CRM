package com.eko.rcrm.dc.calldetect

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.util.Result as AppResult
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Instant

/** For one finished call on this phone: if its number belongs to a CRM official in this DC's
 * territory, log it so it lands in the Pending Queue; otherwise drop it. The number is only
 * ever sent to the backend's territory-scoped lookup - a non-matching (personal) call is
 * discarded here and never stored server-side. */
@HiltWorker
class CallDetectedWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val callRepository: CallRepository,
    private val store: CallDetectionStore
) : CoroutineWorker(context, workerParams) {

    override suspend fun doWork(): Result {
        val number = inputData.getString(KEY_NUMBER)
        if (number.isNullOrBlank()) {
            store.setLastResult(
                "A call was detected but its number wasn't reported - the call-screening role " +
                    "isn't enabled, or this phone didn't screen that call."
            )
            return Result.success()
        }
        val masked = "***" + number.filter { it.isDigit() }.takeLast(4)

        val match = when (val lookup = callRepository.lookupCaller(number)) {
            is AppResult.Success -> lookup.data
            is AppResult.Error -> return retryOrGiveUp("Could not check $masked against the CRM: ${lookup.message}")
        }
        if (match == null) {
            store.setLastResult("Call with $masked ignored - not a CRM contact in your territory.")
            return Result.success()
        }

        val started = inputData.getLong(KEY_STARTED_AT, System.currentTimeMillis())
        val ended = inputData.getLong(KEY_ENDED_AT, System.currentTimeMillis())
        val outgoing = inputData.getBoolean(KEY_OUTGOING, false)

        // Only a call that was actually answered belongs in the CRM queue - a missed/rejected call
        // (only rang) is dropped. Unknown (no call-log permission) is treated as answered so a real
        // call is never silently lost.
        if (CallLogReader.wasAnswered(applicationContext, number, started) == false) {
            store.setLastResult("Call with $masked ignored - it rang but wasn't answered.")
            return Result.success()
        }
        return when (
            val logged = callRepository.logNativeCall(
                phone = number,
                startedAtIso = Instant.ofEpochMilli(started).toString(),
                endedAtIso = Instant.ofEpochMilli(ended).toString(),
                durationSeconds = inputData.getInt(KEY_DURATION, 0),
                direction = if (outgoing) "outbound" else "inbound",
                manual = false
            )
        ) {
            is AppResult.Success -> {
                store.setLastResult("Logged ${if (outgoing) "outgoing" else "incoming"} call with $match - see the Pending Queue.")
                Result.success()
            }
            is AppResult.Error -> retryOrGiveUp("Could not log the call with $match: ${logged.message}")
        }
    }

    private fun retryOrGiveUp(message: String): Result =
        if (runAttemptCount >= MAX_ATTEMPTS) {
            store.setLastResult("$message (gave up - log it manually from Home > Log a call)")
            Result.failure()
        } else {
            Result.retry()
        }

    companion object {
        const val KEY_NUMBER = "number"
        const val KEY_STARTED_AT = "started_at"
        const val KEY_ENDED_AT = "ended_at"
        const val KEY_DURATION = "duration"
        const val KEY_OUTGOING = "outgoing"
        private const val MAX_ATTEMPTS = 4
    }
}
