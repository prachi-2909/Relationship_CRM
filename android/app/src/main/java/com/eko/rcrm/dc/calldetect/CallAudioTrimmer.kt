package com.eko.rcrm.dc.calldetect

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import android.util.Log
import java.io.File
import java.nio.ByteBuffer

/** Trims a recording so only the LAST [keepSeconds] seconds remain - used to drop the ring-back at
 * the start of an outgoing call (the call isn't answered until later, so the real conversation is the
 * tail). Lossless: it copies the encoded samples with MediaExtractor -> MediaMuxer, no re-encode. */
object CallAudioTrimmer {

    private const val TAG = "RCRM:Trimmer"

    /** Returns a new trimmed file (or the original when there's nothing meaningful to trim / on any
     * failure - a full recording is always better than none). */
    fun keepLastSeconds(src: File, keepSeconds: Int): File {
        if (keepSeconds <= 0 || !src.exists()) return src
        var extractor: MediaExtractor? = null
        var muxer: MediaMuxer? = null
        val dst = File(src.parentFile, src.nameWithoutExtension + "_trim." + src.extension)
        try {
            extractor = MediaExtractor().apply { setDataSource(src.absolutePath) }
            val track = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            } ?: return src
            val format = extractor.getTrackFormat(track)
            val totalUs = if (format.containsKey(MediaFormat.KEY_DURATION)) format.getLong(MediaFormat.KEY_DURATION) else 0L
            val keepUs = keepSeconds * 1_000_000L
            val startUs = totalUs - keepUs
            // Nothing worth trimming (recording already ~= talk time, e.g. incoming).
            if (totalUs <= 0L || startUs <= MIN_TRIM_US) return src

            extractor.selectTrack(track)
            extractor.seekTo(startUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            val seekedUs = extractor.sampleTime.takeIf { it >= 0 } ?: return src

            val outputFormat = if (src.extension.equals("ogg", true)) MediaMuxer.OutputFormat.MUXER_OUTPUT_OGG
                else MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4
            muxer = MediaMuxer(dst.absolutePath, outputFormat)
            val outTrack = muxer.addTrack(format)
            muxer.start()

            val buffer = ByteBuffer.allocate(MAX_SAMPLE_BYTES)
            val info = MediaCodec.BufferInfo()
            while (true) {
                val size = extractor.readSampleData(buffer, 0)
                if (size < 0) break
                info.offset = 0
                info.size = size
                info.presentationTimeUs = (extractor.sampleTime - seekedUs).coerceAtLeast(0)
                info.flags = extractor.sampleFlags
                muxer.writeSampleData(outTrack, buffer, info)
                extractor.advance()
            }
            muxer.stop()
            // Replace the original with the trimmed file so the rest of the pipeline is unchanged.
            if (dst.exists() && dst.length() > 0) {
                src.delete()
                if (dst.renameTo(src)) return src
                return dst
            }
            return src
        } catch (t: Throwable) {
            Log.w(TAG, "trim failed, keeping full recording: ${t.message}")
            runCatching { dst.delete() }
            return src
        } finally {
            runCatching { muxer?.release() }
            runCatching { extractor?.release() }
        }
    }

    private const val MIN_TRIM_US = 1_500_000L  // don't bother trimming under ~1.5s of ring
    private const val MAX_SAMPLE_BYTES = 256 * 1024
}
