/*
 * Derived from CallVault (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 *
 * Itself a port of scrcpy's Workarounds.createAudioRecord (Genymobile/scrcpy PR #5154, Apache-2.0).
 */
package com.eko.rcrm.dc.recorder

import android.annotation.SuppressLint
import android.content.AttributionSource
import android.media.AudioAttributes
import android.media.AudioRecord
import android.os.Binder
import android.os.Build
import android.os.Looper
import android.os.Parcel
import java.lang.ref.WeakReference

/**
 * Builds an [AudioRecord] WITHOUT running its public constructor, so vivo's modified constructor
 * (which dereferences a Context the shell-uid recorder host does not have) can't crash capture. Used
 * only after the normal constructor has failed with [VendorConstructorCrash].
 *
 * Hidden-API reflection runs ONLY inside the privileged recorder host (an app_process started as the
 * shell user, like scrcpy's server), never in the app process, so the app's hidden-API policy does
 * not govern it.
 */
@SuppressLint("DiscouragedPrivateApi", "SoonBlockedPrivateApi", "PrivateApi", "BlockedPrivateApi")
internal object BypassedAudioRecord {

    private const val SUBMIX_FIXED_VOLUME = "fixedVolume"

    fun create(
        capturePreset: Int,
        tags: List<String>,
        sampleRate: Int,
        channelMask: Int,
        channelCount: Int,
        encoding: Int,
        bufferSizeInBytes: Int,
    ): AudioRecord {
        val cls = AudioRecord::class.java
        val record = cls.getDeclaredConstructor(Long::class.javaPrimitiveType).apply { isAccessible = true }
            .newInstance(0L)

        field("mRecordingState").set(record, AudioRecord.RECORDSTATE_STOPPED)
        field("mInitializationLooper").set(record, Looper.myLooper() ?: Looper.getMainLooper())

        val fullVolume = tags.any { it.equals(SUBMIX_FIXED_VOLUME, ignoreCase = true) }
        if (fullVolume) runCatching { field("mIsSubmixFullVolume").setBoolean(record, true) }

        val ab = AudioAttributes.Builder()
        AudioAttributes.Builder::class.java.getMethod("setInternalCapturePreset", Int::class.javaPrimitiveType)
            .invoke(ab, capturePreset)
        val addTag = AudioAttributes.Builder::class.java.getMethod("addTag", String::class.java)
        tags.filterNot { it.equals(SUBMIX_FIXED_VOLUME, ignoreCase = true) }.forEach { addTag.invoke(ab, it) }
        val attributes = ab.build()
        field("mAudioAttributes").set(record, attributes)

        cls.getDeclaredMethod("audioParamCheck", Int::class.javaPrimitiveType, Int::class.javaPrimitiveType, Int::class.javaPrimitiveType)
            .apply { isAccessible = true }.invoke(record, capturePreset, sampleRate, encoding)
        field("mChannelCount").setInt(record, channelCount)
        field("mChannelMask").setInt(record, channelMask)
        cls.getDeclaredMethod("audioBuffSizeCheck", Int::class.javaPrimitiveType)
            .apply { isAccessible = true }.invoke(record, bufferSizeInBytes)

        val rates = intArrayOf(sampleRate)
        val session = intArrayOf(android.media.AudioManager.AUDIO_SESSION_ID_GENERATE)
        val nativeBuffer = field("mNativeBufferSizeInBytes").getInt(record)
        val result = nativeSetup(record, attributes, rates, channelMask, record.audioFormat, nativeBuffer, session)
        check(result == AudioRecord.SUCCESS) { "native_setup returned $result" }

        field("mSampleRate").setInt(record, rates[0])
        field("mSessionId").setInt(record, session[0])
        field("mState").setInt(record, AudioRecord.STATE_INITIALIZED)
        return record
    }

    private fun field(name: String) =
        AudioRecord::class.java.getDeclaredField(name).apply { isAccessible = true }

    private fun nativeSetup(
        record: AudioRecord, attributes: AudioAttributes, rates: IntArray, channelMask: Int,
        format: Int, bufferBytes: Int, session: IntArray,
    ): Int {
        val cls = AudioRecord::class.java
        val i = Int::class.javaPrimitiveType
        val l = Long::class.javaPrimitiveType
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            val opPackage = runCatching {
                Class.forName("android.app.ActivityThread").getMethod("currentOpPackageName").invoke(null) as String?
            }.getOrNull()
            return cls.getDeclaredMethod("native_setup", Any::class.java, Any::class.java, IntArray::class.java, i, i, i, i,
                IntArray::class.java, String::class.java, l).apply { isAccessible = true }
                .invoke(record, WeakReference(record), attributes, rates, channelMask, 0, format, bufferBytes, session, opPackage, 0L) as Int
        }
        var source = AttributionSource.myAttributionSource()
        if (source.packageName == null) {
            source = runCatching {
                AttributionSource::class.java.getMethod("withPackageName", String::class.java)
                    .invoke(source, "uid:" + Binder.getCallingUid()) as AttributionSource
            }.getOrDefault(source)
        }
        val state = AttributionSource::class.java.getDeclaredMethod("asScopedParcelState").apply { isAccessible = true }
            .invoke(source) as AutoCloseable
        return state.use {
            val parcel = it.javaClass.getDeclaredMethod("getParcel").apply { isAccessible = true }.invoke(it) as Parcel
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                cls.getDeclaredMethod("native_setup", Any::class.java, Any::class.java, IntArray::class.java, i, i, i, i,
                    IntArray::class.java, Parcel::class.java, l, i).apply { isAccessible = true }
                    .invoke(record, WeakReference(record), attributes, rates, channelMask, 0, format, bufferBytes, session, parcel, 0L, 0) as Int
            } else {
                cls.getDeclaredMethod("native_setup", Any::class.java, Any::class.java, IntArray::class.java, i, i, i, i,
                    IntArray::class.java, Parcel::class.java, l, i, i).apply { isAccessible = true }
                    .invoke(record, WeakReference(record), attributes, rates, channelMask, 0, format, bufferBytes, session, parcel, 0L, 0, 0) as Int
            }
        }
    }
}
