/*
 * Derived from CallVault's RecorderServiceImpl (a fork of ShizuCallRecorder,
 * Copyright (C) kitsumed (Med)), GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.os.ParcelFileDescriptor
import android.os.Process
import android.util.Log
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.system.exitProcess

/**
 * The call-audio recorder as it runs in the privileged (shell-uid) process Shizuku spawns. The app
 * hands it a file descriptor; it opens the VOICE_CALL stream and writes the encoded recording there.
 * Runs on a worker thread so the binder thread never blocks on capture setup/teardown.
 */
open class RecorderServiceImpl(private val apkPath: String) : IRecorderService.Stub() {

    private val recordingActive = AtomicBoolean(false)
    @Volatile private var recorder: DirectCallRecorder? = null
    private val worker = java.util.concurrent.Executors.newSingleThreadExecutor()

    override fun startRecording(source: String?, codec: String?, bitRate: Int, outFd: ParcelFileDescriptor?) {
        if (outFd == null || source == null || codec == null) { Log.e(TAG, "startRecording: null arg"); return }
        if (!recordingActive.compareAndSet(false, true)) { Log.w(TAG, "already recording"); return }
        val src = CaptureSource.fromKey(source)
        val cod = CaptureCodec.fromKey(codec)
        worker.execute {
            val rec = runCatching {
                DirectCallRecorder(src, cod, bitRate, outFd).also { it.start() }
            }.onFailure {
                Log.e(TAG, "startRecording failed: ${it.message}", it)
                runCatching { outFd.close() }
                recordingActive.set(false)
            }.getOrNull()
            recorder = rec
        }
    }

    override fun stopRecording() {
        if (!recordingActive.compareAndSet(true, false)) return
        val done = CountDownLatch(1)
        worker.execute {
            runCatching { recorder?.stop() }.onFailure { Log.w(TAG, "stop error: ${it.message}") }
            recorder = null
            done.countDown()
        }
        runCatching { done.await(STOP_AWAIT_MS, TimeUnit.MILLISECONDS) }
    }

    override fun isRecording(): Boolean = recordingActive.get()

    override fun destroy() {
        Log.i(TAG, "destroy; stopping and exiting host")
        stopRecording()
        worker.execute { exitProcess(0) }
    }

    override fun hostUid(): Int = Process.myUid()
    override fun hostApkPath(): String = apkPath
    override fun killStaleRecorders() { /* single Shizuku-hosted service; nothing to reconcile */ }

    protected companion object {
        const val TAG = "RCRM:RecorderHost"
        const val STOP_AWAIT_MS = 6000L
    }
}
