/*
 * Derived from CallVault's RecorderBinderProvider (a fork of ShizuCallRecorder,
 * Copyright (C) kitsumed (Med)), GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.net.Uri
import android.os.Bundle
import android.os.IBinder
import android.os.Process
import android.util.Log

/** Exported ContentProvider that RECEIVES the shell-uid daemon's binder. The daemon ([RecorderServer])
 * is a non-app process, so - exactly like Shizuku - it resolves this provider and calls
 * "sendBinder". Exported=true is required for that cross-process delivery; only "sendBinder" is
 * honoured and no app data is exposed. */
class RecorderBinderProvider : ContentProvider() {

    override fun onCreate(): Boolean = true

    override fun call(method: String, arg: String?, extras: Bundle?): Bundle {
        if (method == METHOD_SEND_BINDER && extras != null) {
            // Set the classloader or BinderContainer unmarshals to null (the classic Shizuku gotcha).
            extras.classLoader = BinderContainer::class.java.classLoader
            @Suppress("DEPRECATION")
            val binder: IBinder? = extras.getParcelable<BinderContainer>(EXTRA_BINDER)?.binder
            if (binder != null) {
                RecorderConnection.onBinderReceived(IRecorderService.Stub.asInterface(binder))
                runCatching { binder.linkToDeath(RecorderConnection.deathRecipient, 0) }
                Log.i(TAG, "received daemon binder (pid=${Process.myPid()} uid=${Process.myUid()})")
            } else {
                Log.e(TAG, "sendBinder: container/binder null (classloader/SELinux?)")
            }
        }
        return Bundle()
    }

    // Unused provider surface.
    override fun query(uri: Uri, p: Array<String>?, s: String?, a: Array<String>?, o: String?): Cursor? = null
    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, s: String?, a: Array<String>?): Int = 0
    override fun update(uri: Uri, v: ContentValues?, s: String?, a: Array<String>?): Int = 0

    companion object {
        private const val TAG = "RCRM:BinderProvider"
        const val AUTHORITY_SUFFIX = ".recorder.binder"
        const val METHOD_SEND_BINDER = "sendBinder"
        const val EXTRA_BINDER = "binder"
    }
}
