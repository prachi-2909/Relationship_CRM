/*
 * Ported from CallVault (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * licensed under the GNU General Public License v3 or later. See NOTICE in the project root.
 * This file, as part of the SBI Relationship CRM, is therefore also GPL-3.0-or-later.
 */
package com.eko.rcrm.dc.recorder;

/**
 * The binder the app and the shell-uid recorder process (hosted by Shizuku) talk over. Trimmed from
 * CallVault's IRecorderService to the direct call-audio capture path; the app passes a file
 * descriptor and the privileged process writes the encoded recording into it.
 */
interface IRecorderService {
    void startRecording(String source, String codec, int bitRate, in ParcelFileDescriptor outFd);
    void stopRecording();
    boolean isRecording();
    void destroy();
    int hostUid();
    String hostApkPath();
    void killStaleRecorders();
}
