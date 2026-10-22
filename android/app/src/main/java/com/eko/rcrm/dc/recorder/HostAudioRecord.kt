/*
 * Derived from CallVault (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.annotation.SuppressLint
import android.media.AudioRecord
import android.util.Log

/** The one way the recorder host opens an [AudioRecord]. Tries the public constructor first, and
 * only on vivo's no-Context constructor crash ([VendorConstructorCrash]) rebuilds the same record
 * through [BypassedAudioRecord]. Any other failure returns null. */
internal object HostAudioRecord {

    private const val TAG = "RCRM:HostAudioRecord"

    @SuppressLint("MissingPermission")
    fun open(what: String, source: Int, sampleRate: Int, channelMask: Int, encoding: Int, bufferBytes: Int): AudioRecord? {
        val normal = runCatching { AudioRecord(source, sampleRate, channelMask, encoding, bufferBytes) }
        normal.getOrNull()?.let { return it }
        val error = normal.exceptionOrNull()!!
        if (!VendorConstructorCrash.matches(error)) {
            Log.w(TAG, "$what: AudioRecord(source=$source) threw: ${error.javaClass.simpleName}: ${error.message}")
            return null
        }
        Log.w(TAG, "$what: ROM AudioRecord constructor crashed without a Context; building it the other way")
        return runCatching {
            BypassedAudioRecord.create(
                capturePreset = source,
                tags = emptyList(),
                sampleRate = sampleRate,
                channelMask = channelMask,
                channelCount = Integer.bitCount(channelMask),
                encoding = encoding,
                bufferSizeInBytes = bufferBytes,
            )
        }.onFailure { Log.e(TAG, "$what: building without the vendor constructor failed too: ${it.message}", it) }
            .getOrNull()
    }
}
