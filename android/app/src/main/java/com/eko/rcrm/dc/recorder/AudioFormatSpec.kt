/*
 * Derived from CallVault (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.media.MediaFormat
import android.media.MediaMuxer
import android.media.MediaRecorder

/** The audio source + codec the privileged recorder uses, distilled from CallVault's
 * ScrcpyAudioSource / ScrcpyAudioCodec to just what the direct capture pipeline needs. */
enum class CaptureSource(val key: String, val androidSource: Int) {
    /** Both sides of a phone call - the privileged stream only a shell-uid/system process may open. */
    VOICE_CALL("voice-call", MediaRecorder.AudioSource.VOICE_CALL),
    /** The processed voice-comm mic; fallback where VOICE_CALL is refused. */
    VOICE_COMMUNICATION("voice-communication", MediaRecorder.AudioSource.VOICE_COMMUNICATION);

    companion object {
        fun fromKey(key: String): CaptureSource = entries.firstOrNull { it.key == key } ?: VOICE_CALL
    }
}

enum class CaptureCodec(
    val key: String,
    val mimeType: String,
    val outputFormat: Int,
    val containerExtension: String,
    val defaultBitRate: Int,
) {
    OPUS("opus", MediaFormat.MIMETYPE_AUDIO_OPUS, MediaMuxer.OutputFormat.MUXER_OUTPUT_OGG, ".ogg", 24_000),
    AAC("aac", MediaFormat.MIMETYPE_AUDIO_AAC, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4, ".m4a", 32_000);

    companion object {
        fun fromKey(key: String): CaptureCodec = entries.firstOrNull { it.key == key } ?: OPUS
    }
}
