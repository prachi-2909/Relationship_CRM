/*
 * Derived from CallVault's RecorderUserService (a fork of ShizuCallRecorder,
 * Copyright (C) kitsumed (Med)), GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.content.Context
import androidx.annotation.Keep
import com.eko.rcrm.dc.BuildConfig

/**
 * The recorder as Shizuku starts it: Shizuku spawns a shell-uid process with our APK on the
 * classpath and instantiates THIS class, handing the binder back to the app. Both constructors must
 * survive minification (hence [Keep]) because nothing references this class by name.
 */
@Keep
class RecorderUserService : RecorderServiceImpl {

    @Keep constructor() : super(apkFromClasspath())

    /** Shizuku API v13+ hands a Context; its sourceDir is a reliable APK path (unlike the classpath,
     * which can name Shizuku's own APK in a hosted process). */
    @Keep constructor(context: Context) : super(context.applicationInfo.sourceDir)

    private companion object {
        fun apkFromClasspath(): String {
            val cp = runCatching { System.getProperty("java.class.path") }.getOrNull().orEmpty()
            return cp.split(':').firstOrNull { it.endsWith(".apk") && it.contains(BuildConfig.APPLICATION_ID) }.orEmpty()
        }
    }
}
