/*
 * Derived from CallVault's ShizukuBackend (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.content.ComponentName
import android.content.Context
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.IBinder
import android.util.Log
import com.eko.rcrm.dc.BuildConfig
import rikka.shizuku.Shizuku
import rikka.shizuku.ShizukuProvider

/** Starts the recorder through Shizuku and takes the binder it hands back. Nothing here throws: a
 * phone without Shizuku, with it stopped, or with permission denied is an ordinary state for a
 * feature that is off by default. */
object ShizukuBackend {
    private const val TAG = "RCRM:ShizukuBackend"
    const val PERMISSION_REQUEST_CODE = 5713
    private const val SHIZUKU_PACKAGE = "moe.shizuku.privileged.api"

    private val userServiceArgs by lazy {
        Shizuku.UserServiceArgs(ComponentName(BuildConfig.APPLICATION_ID, RecorderUserService::class.java.name))
            .daemon(true)
            .processNameSuffix("recorder")
            .version(BuildConfig.VERSION_CODE)
    }

    @Volatile private var connection: ServiceConnection? = null
    private val bindLock = Any()

    fun isInstalled(context: Context): Boolean = runCatching {
        context.packageManager.getPermissionInfo(ShizukuProvider.PERMISSION, 0).packageName != null
    }.getOrDefault(runCatching { context.packageManager.getPackageInfo(SHIZUKU_PACKAGE, 0); true }.getOrDefault(false))

    fun isRunning(): Boolean = runCatching { Shizuku.pingBinder() }.getOrDefault(false)

    fun hasPermission(): Boolean = runCatching {
        Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
    }.getOrDefault(false)

    fun requestPermission() {
        runCatching { Shizuku.requestPermission(PERMISSION_REQUEST_CODE) }
            .onFailure { Log.w(TAG, "requestPermission failed: ${it.message}") }
    }

    fun start(): Boolean = synchronized(bindLock) {
        if (!isRunning() || !hasPermission()) return false
        if (connection != null) return true
        val conn = object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
                synchronized(bindLock) {
                    if (connection !== this || binder == null || !binder.pingBinder()) return
                    RecorderConnection.onBinderReceived(IRecorderService.Stub.asInterface(binder))
                    runCatching { binder.linkToDeath(RecorderConnection.deathRecipient, 0) }
                }
            }
            override fun onServiceDisconnected(name: ComponentName?) {
                synchronized(bindLock) { if (connection === this) RecorderConnection.onBinderDied() }
            }
        }
        connection = conn
        return runCatching { Shizuku.bindUserService(userServiceArgs, conn); true }
            .onFailure { connection = null; Log.e(TAG, "bindUserService failed: ${it.message}") }
            .getOrDefault(false)
    }

    fun stop(remove: Boolean = true): Unit = synchronized(bindLock) {
        val conn = connection ?: NO_OP
        runCatching { Shizuku.unbindUserService(userServiceArgs, conn, remove) }
            .onFailure { Log.w(TAG, "unbindUserService failed: ${it.message}") }
        connection = null
        RecorderConnection.onBinderDied()
    }

    private val NO_OP = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, service: IBinder?) = Unit
        override fun onServiceDisconnected(name: ComponentName?) = Unit
    }
}
