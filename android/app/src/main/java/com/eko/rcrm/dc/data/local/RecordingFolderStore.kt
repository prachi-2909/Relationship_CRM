package com.eko.rcrm.dc.data.local

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** The folder the DC's call-recorder app saves into, chosen once through Android's folder picker
 * (so access is limited to exactly that one folder - no broad storage permission). */
@Singleton
class RecordingFolderStore @Inject constructor(
    @ApplicationContext context: Context
) {
    private val prefs = context.getSharedPreferences("recording_folder", Context.MODE_PRIVATE)

    var treeUri: String?
        get() = prefs.getString(KEY_URI, null)
        set(value) { prefs.edit().putString(KEY_URI, value).apply() }

    private companion object {
        const val KEY_URI = "tree_uri"
    }
}
