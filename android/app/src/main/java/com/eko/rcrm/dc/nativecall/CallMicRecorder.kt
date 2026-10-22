package com.eko.rcrm.dc.nativecall

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File

/** EXPERIMENT: records the DC's microphone for the length of a native-SIM call. Android never
 * hands a third-party app the call's own audio stream, so this can only pick up whatever the
 * phone's mic hears - the DC's voice, plus the other person only if the call is on speaker,
 * and on many devices/Android versions the OS silences mic capture during a call entirely.
 * [stop] therefore reports the peak amplitude seen, so a silent recording can be told apart
 * from a real one instead of uploading an empty file. */
class CallMicRecorder(private val context: Context) {

    data class Outcome(val file: File?, val peakAmplitude: Int, val seconds: Int, val error: Throwable?)

    private var recorder: MediaRecorder? = null
    private var file: File? = null
    private var sampler: Job? = null
    private var startedAtMs = 0L

    @Volatile
    private var peak = 0

    /** Returns null on success, or the exception that stopped recording from starting. */
    fun start(scope: CoroutineScope, callSessionId: Int): Throwable? {
        return try {
            val dir = File(context.filesDir, "voice_notes").apply { mkdirs() }
            val out = File(dir, "callrec_${callSessionId}_${System.currentTimeMillis()}.m4a")
            @Suppress("DEPRECATION")
            val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(context) else MediaRecorder()
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioEncodingBitRate(64_000)
            r.setAudioSamplingRate(16_000)
            r.setOutputFile(out.absolutePath)
            r.prepare()
            r.start()
            recorder = r
            file = out
            startedAtMs = System.currentTimeMillis()
            peak = 0
            sampler = scope.launch {
                while (isActive) {
                    delay(500)
                    val amplitude = try { r.maxAmplitude } catch (_: Throwable) { 0 }
                    if (amplitude > peak) peak = amplitude
                }
            }
            null
        } catch (t: Throwable) {
            release()
            file?.delete()
            file = null
            t
        }
    }

    fun stop(): Outcome {
        sampler?.cancel()
        sampler = null
        val seconds = if (startedAtMs > 0) ((System.currentTimeMillis() - startedAtMs) / 1000).toInt() else 0
        var error: Throwable? = null
        try {
            recorder?.stop()
        } catch (t: Throwable) {
            // stop() throws when too little audio was captured to form a valid file.
            error = t
        }
        release()
        if (error != null) file?.delete()
        val result = Outcome(file?.takeIf { it.exists() && error == null }, peak, seconds, error)
        recorder = null
        startedAtMs = 0L
        return result
    }

    private fun release() {
        try {
            recorder?.release()
        } catch (_: Throwable) {
        }
        recorder = null
    }
}
