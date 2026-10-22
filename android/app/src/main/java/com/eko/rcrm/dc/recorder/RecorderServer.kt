/*
 * Derived from CallVault's RecorderServer (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.os.Looper
import android.os.Process
import androidx.annotation.Keep

/**
 * app_process entrypoint for the privileged (shell-uid) recorder daemon in built-in / embedded-ADB
 * mode. Launched DETACHED over the app's own ADB shell as
 *   `CLASSPATH=<apk> app_process / com.eko.rcrm.dc.recorder.RecorderServer <apk> <authority>`
 * It builds [RecorderServiceImpl] and PUSHES its binder to the app's [RecorderBinderProvider] the
 * same way Shizuku's server delivers its binder - after which the app drives recording over binder
 * with no further ADB, even while Wireless Debugging is off.
 */
@Keep
object RecorderServer {
    private const val TAG = "RCRM:RecorderServer"

    @JvmStatic
    fun main(args: Array<String>) {
        println("RecorderServer starting pid=${Process.myPid()} uid=${Process.myUid()} args=${args.joinToString(",")}")
        if (args.isEmpty()) { println("$TAG: expected <apkPath> [authority]"); return }
        val apkPath = args[0]
        val authority = args.getOrNull(1) ?: return
        try {
            Looper.prepareMainLooper()
            val stub = RecorderServiceImpl(apkPath)
            val delivered = BinderDelivery.deliverBinderToApp(stub.asBinder(), authority)
            println("$TAG: binder delivery ok=$delivered; entering loop")
            Looper.loop()
        } catch (t: Throwable) {
            println("$TAG: fatal ${t.message}")
        }
    }
}
