/*
 * Derived from CallVault's DirectAudioRecorderSession (a fork of ShizuCallRecorder,
 * Copyright (C) kitsumed (Med)), GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 *
 * Distilled to the direct capture path: speaker labelling, the overrun ledger and the scrcpy
 * fallback are not included.
 */
package com.eko.rcrm.dc.recorder

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaFormat
import android.media.MediaMuxer
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.os.ParcelFileDescriptor
import android.os.Process
import android.util.Log
import java.util.concurrent.atomic.AtomicBoolean

/** Captures a call's audio from [source] (VOICE_CALL = both sides) in the privileged host process and
 * writes it, encoded as [codec], into [outFd]. Stereo is captured when the route allows (uplink on
 * one channel, downlink on the other) and down-mixed to mono so the whole bitrate serves the voice. */
internal class DirectCallRecorder(
    private val source: CaptureSource,
    private val codec: CaptureCodec,
    private val bitRate: Int,
    private val outFd: ParcelFileDescriptor,
) {
    private val stopRequested = AtomicBoolean(false)
    private val readerFinished = AtomicBoolean(false)
    @Volatile private var audioRecord: AudioRecord? = null
    @Volatile private var encoder: MediaCodec? = null
    @Volatile private var muxer: MediaMuxer? = null
    @Volatile private var readThread: Thread? = null
    @Volatile private var encodeThread: Thread? = null
    @Volatile private var noiseSuppressor: NoiseSuppressor? = null
    @Volatile private var agc: AutomaticGainControl? = null
    @Volatile private var aec: AcousticEchoCanceler? = null
    private val queue = java.util.concurrent.ArrayBlockingQueue<ByteArray>(QUEUE_CAPACITY)

    fun start() {
        val (record, captureChannels) = openRecord()
        audioRecord = record
        attachNoiseReduction(record)
        val mime = codec.mimeType
        val enc = openEncoder(mime, EncoderLimits.resolve(mime, bitRate))
        encoder = enc
        val mux = MediaMuxer(outFd.fileDescriptor, codec.outputFormat)
        muxer = mux
        enc.start()
        record.startRecording()
        check(record.recordingState == AudioRecord.RECORDSTATE_RECORDING) { "AudioRecord did not enter RECORDING" }

        encodeThread = Thread { runCatching { encodeLoop(enc, mux, captureChannels) }.onFailure { Log.w(TAG, "encode ended: ${it.message}") } }
            .apply { isDaemon = true; name = "rcrm-cap-encode"; start() }
        readThread = Thread { runCatching { readLoop(record, captureChannels) }.onFailure { Log.w(TAG, "read ended: ${it.message}") } }
            .apply { isDaemon = true; name = "rcrm-cap-read"; start() }
    }

    /** Deliberately attaches NOTHING. NoiseSuppressor / AutomaticGainControl / AcousticEchoCanceler
     * are MICROPHONE effects: they assume the near-end mic as input and the far-end as a reference
     * to subtract. On a VOICE_CALL source the stream is already both sides mixed by the modem, so
     * AEC treats the near-end (your own voice) as "echo" and cancels it - which is exactly the
     * "far party records, my own voice missing" symptom. These effects must never touch call audio;
     * loudness is handled purely in software by PcmDownmix.applyGain in the encode loop. */
    private fun attachNoiseReduction(record: AudioRecord) {
        // intentionally empty - see the doc comment above.
    }

    fun stop() {
        stopRequested.set(true)
        runCatching { readThread?.join(READ_JOIN_MS) }
        runCatching { noiseSuppressor?.release() }
        runCatching { agc?.release() }
        runCatching { aec?.release() }
        runCatching { audioRecord?.stop() }
        runCatching { audioRecord?.release() }
        readerFinished.set(true)
        runCatching { encodeThread?.join(ENCODE_JOIN_MS) }
        runCatching { encoder?.stop() }
        runCatching { encoder?.release() }
        runCatching { muxer?.stop() }
        runCatching { muxer?.release() }
        runCatching { outFd.close() }
    }

    private fun openRecord(): Pair<AudioRecord, Int> {
        for (mask in intArrayOf(AudioFormat.CHANNEL_IN_STEREO, AudioFormat.CHANNEL_IN_MONO)) {
            val channels = if (mask == AudioFormat.CHANNEL_IN_STEREO) 2 else 1
            val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, mask, AudioFormat.ENCODING_PCM_16BIT)
            if (minBuf <= 0) continue
            val rec = HostAudioRecord.open("call capture", source.androidSource, SAMPLE_RATE, mask,
                AudioFormat.ENCODING_PCM_16BIT, minBuf * BUFFER_FACTOR)
            if (rec != null && rec.state == AudioRecord.STATE_INITIALIZED) return rec to channels
            runCatching { rec?.release() }
        }
        throw IllegalStateException("AudioRecord would not initialise for source ${source.androidSource}")
    }

    private fun openEncoder(mime: String, rate: Int): MediaCodec {
        val fmt = MediaFormat.createAudioFormat(mime, SAMPLE_RATE, ENCODE_CHANNELS).apply {
            setInteger(MediaFormat.KEY_BIT_RATE, rate)
            if (mime == MediaFormat.MIMETYPE_AUDIO_AAC) setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
            setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16_384)
        }
        val c = MediaCodec.createEncoderByType(mime)
        c.configure(fmt, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        return c
    }

    private fun readLoop(record: AudioRecord, captureChannels: Int) {
        runCatching { Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO) }
        val pcm = ByteArray(READ_CHUNK_BYTES)
        while (!stopRequested.get()) {
            val read = record.read(pcm, 0, pcm.size)
            if (read <= 0) continue
            queue.offer(pcm.copyOf(read))
        }
        readerFinished.set(true)
    }

    private fun encodeLoop(enc: MediaCodec, mux: MediaMuxer, captureChannels: Int) {
        val info = MediaCodec.BufferInfo()
        var muxerStarted = false
        var track = -1
        var totalFrames = 0L
        val downmix = captureChannels == 2
        val mono = ByteArray(READ_CHUNK_BYTES / 2)
        val bytesPerFrame = 2 * ENCODE_CHANNELS

        while (true) {
            val chunk = queue.poll(TAKE_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS)
            if (chunk == null) { if (readerFinished.get() && queue.isEmpty()) break else continue }
            val (buf, len) = if (downmix) mono to PcmDownmix.stereoToMono(chunk, chunk.size, mono) else chunk to chunk.size
            // Call audio (VOICE_CALL) is often very quiet on many phones, which leaves the transcriber
            // nothing to work with. Amplify the PCM (with hard clipping) so the voice is clearly audible.
            PcmDownmix.applyGain(buf, len, GAIN)
            val inIdx = enc.dequeueInputBuffer(DEQUEUE_TIMEOUT_US)
            if (inIdx >= 0) {
                enc.getInputBuffer(inIdx)!!.apply { clear(); put(buf, 0, len) }
                enc.queueInputBuffer(inIdx, 0, len, totalFrames * 1_000_000L / SAMPLE_RATE, 0)
                totalFrames += len / bytesPerFrame
            }
            val r = drain(enc, mux, info, muxerStarted, track); muxerStarted = r.first; track = r.second
        }
        val inIdx = enc.dequeueInputBuffer(END_OF_STREAM_TIMEOUT_US)
        if (inIdx >= 0) enc.queueInputBuffer(inIdx, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
        drain(enc, mux, info, muxerStarted, track, drainToEos = true)
    }

    private fun drain(enc: MediaCodec, mux: MediaMuxer, info: MediaCodec.BufferInfo, startedIn: Boolean, trackIn: Int, drainToEos: Boolean = false): Pair<Boolean, Int> {
        var started = startedIn; var track = trackIn
        while (true) {
            val outIdx = enc.dequeueOutputBuffer(info, if (drainToEos) END_OF_STREAM_TIMEOUT_US else 0)
            when {
                outIdx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> { track = mux.addTrack(enc.outputFormat); mux.start(); started = true }
                outIdx == MediaCodec.INFO_TRY_AGAIN_LATER -> { if (drainToEos) continue else return started to track }
                outIdx >= 0 -> {
                    val out = enc.getOutputBuffer(outIdx)!!
                    val isConfig = info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0
                    if (!isConfig && info.size > 0 && started) {
                        out.position(info.offset); out.limit(info.offset + info.size)
                        mux.writeSampleData(track, out, info)
                    }
                    enc.releaseOutputBuffer(outIdx, false)
                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) return started to track
                }
            }
        }
    }

    private companion object {
        const val TAG = "RCRM:DirectCapture"
        const val SAMPLE_RATE = 48_000
        const val ENCODE_CHANNELS = 1
        const val READ_CHUNK_BYTES = 4096
        const val GAIN = 3.0f  // amplify quiet call audio ~3x (clipped) so speech is clear for transcription
        const val BUFFER_FACTOR = 4
        const val QUEUE_CAPACITY = 240
        const val DEQUEUE_TIMEOUT_US = 10_000L
        const val END_OF_STREAM_TIMEOUT_US = 100_000L
        const val TAKE_TIMEOUT_MS = 100L
        const val READ_JOIN_MS = 2_000L
        const val ENCODE_JOIN_MS = 5_000L
    }
}

/** PCM-16 helpers for the capture pipeline. */
internal object PcmDownmix {
    /** Multiplies PCM-16 samples by [gain] in place, clamping to the 16-bit range (prevents wrap). */
    fun applyGain(buf: ByteArray, len: Int, gain: Float) {
        if (gain == 1f) return
        var i = 0
        while (i + 1 < len) {
            val s = (buf[i].toInt() and 0xFF or (buf[i + 1].toInt() shl 8)).toShort().toInt()
            val amp = (s * gain).toInt().coerceIn(-32768, 32767)
            buf[i] = (amp and 0xFF).toByte()
            buf[i + 1] = ((amp shr 8) and 0xFF).toByte()
            i += 2
        }
    }

    fun stereoToMono(src: ByteArray, srcLen: Int, dst: ByteArray): Int {
        var di = 0; var si = 0
        while (si + 3 < srcLen) {
            val l = (src[si].toInt() and 0xFF or (src[si + 1].toInt() shl 8)).toShort().toInt()
            val r = (src[si + 2].toInt() and 0xFF or (src[si + 3].toInt() shl 8)).toShort().toInt()
            val m = (l + r) / 2
            dst[di] = (m and 0xFF).toByte(); dst[di + 1] = ((m shr 8) and 0xFF).toByte()
            di += 2; si += 4
        }
        return di
    }
}

/** Picks a bit rate the encoder will accept, falling back to the codec's own recommendation. */
internal object EncoderLimits {
    fun resolve(mime: String, requested: Int): Int {
        return runCatching {
            val info = MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos.firstOrNull { it.isEncoder && it.supportedTypes.any { t -> t.equals(mime, true) } }
            val range = info?.getCapabilitiesForType(mime)?.audioCapabilities?.bitrateRange
            if (range != null) requested.coerceIn(range.lower, range.upper) else requested
        }.getOrDefault(requested)
    }
}
