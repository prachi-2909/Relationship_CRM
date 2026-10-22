package com.eko.rcrm.dc.data.local

import android.content.Context
import androidx.work.WorkManager
import com.eko.rcrm.dc.data.local.db.AppDatabase
import com.eko.rcrm.dc.work.UploadScheduler
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** Erases every piece of DC data this app keeps on the phone. Called on logout and on a forced
 * session end (a 401), so a shared or handed-over device never carries the previous DC's data into
 * the next session - the gap a bank-grade / DPDP review flags. Safe to call from a background
 * thread; each step is independent so one failure can't block the rest. */
@Singleton
class LocalDataWiper @Inject constructor(
    @ApplicationContext private val context: Context,
    private val database: AppDatabase,
    private val callAudioStore: CallAudioStore,
    private val tokenStore: TokenStore
) {
    fun wipe() {
        runCatching { database.clearAllTables() }           // queued uploads, armed calls
        runCatching { callAudioStore.purgeAll() }           // recordings + voice notes + cache copies
        runCatching { WorkManager.getInstance(context).cancelAllWorkByTag(UploadScheduler.TAG_UPLOAD) }
        // Plain prefs that hold phone numbers / names / recording settings.
        for (name in PLAIN_PREFS) {
            runCatching { context.getSharedPreferences(name, Context.MODE_PRIVATE).edit().clear().commit() }
        }
        runCatching { tokenStore.clear() }                  // the bearer token itself
    }

    private companion object {
        val PLAIN_PREFS = listOf("call_detection", "recording_folder", "call_recording")
    }
}
