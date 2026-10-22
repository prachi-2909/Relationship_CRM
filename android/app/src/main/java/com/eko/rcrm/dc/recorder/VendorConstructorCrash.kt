/*
 * Derived from CallVault (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

/**
 * Whether a throwable is the crash vivo put into `AudioRecord`'s public constructor
 * (`VivoAudioRecordImpl.isSupportSubMixRecording()` dereferencing a Context the recorder host does
 * not have). Recognised by shape, not by brand: a NullPointerException thrown from inside code the
 * constructor called, with `AudioRecord.<init>` below the throwing frame.
 */
internal object VendorConstructorCrash {

    fun matches(error: Throwable): Boolean {
        val root = rootCause(error)
        if (root !is NullPointerException) return false
        val frames = root.stackTrace
        val ctor = frames.indexOfFirst { it.className == "android.media.AudioRecord" && it.methodName == "<init>" }
        return ctor > 0 && frames[0].className != "android.media.AudioRecord"
    }

    fun rootCause(error: Throwable): Throwable {
        var e = error
        while (e.cause != null && e.cause !== e) e = e.cause!!
        return e
    }
}
