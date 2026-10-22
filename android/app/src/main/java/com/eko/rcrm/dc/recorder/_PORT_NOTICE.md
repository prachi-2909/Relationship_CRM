Files in this package are DERIVED FROM CallVault (https://github.com/madkongo/CallVault), a fork of
ShizuCallRecorder (https://github.com/kitsumed/ShizuCallRecorder, Copyright (C) kitsumed (Med)),
licensed under the GNU General Public License v3 or later with additional Section 7 terms.

Because this code is incorporated here, the SBI Relationship CRM Android app is a combined work
licensed under GPL-3.0-or-later. The required attribution ("This software is a fork of
ShizuCallRecorder, available at https://github.com/kitsumed/ShizuCallRecorder") is shown in the
app's About screen (see ui/about/AboutScreen.kt).

What was ported: the privileged-process call-audio capture pipeline (AudioRecord VOICE_CALL ->
MediaCodec -> MediaMuxer), the vivo no-Context AudioRecord bypass, and the Shizuku privilege binding.
NOT ported: embedded-ADB self-pairing, the scrcpy-server fallback, the native audio-handoff library,
VoIP/app-call capture, and speaker labelling.
