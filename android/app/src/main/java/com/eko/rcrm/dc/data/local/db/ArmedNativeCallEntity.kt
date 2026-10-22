package com.eko.rcrm.dc.data.local.db

import androidx.room.Entity
import androidx.room.PrimaryKey

object ArmedNativeCallState {
    const val ARMED = "armed"
    const val IN_PROGRESS = "in_progress"
}

/** At most one row ever exists - the Call button is disabled while one is armed, so any
 * OFFHOOK->IDLE cycle NativeCallForegroundService observes while this row exists is
 * unambiguously this call, with zero dependency on CallLog/number-matching. If the process is
 * killed mid-call anyway, this row simply outlives it (state stays IN_PROGRESS) rather than
 * vanishing silently - there is no UI yet that surfaces an orphaned row to the DC on next
 * launch (a real gap, not handled by this phase); currentArmedNativeCall() is there for that
 * to be built against later. */
@Entity(tableName = "armed_native_calls")
data class ArmedNativeCallEntity(
    @PrimaryKey
    val callSessionId: Int,
    val phone: String,
    val armedAtEpochMs: Long,
    val state: String
)
