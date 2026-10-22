/*
 * Derived from CallVault's BinderDelivery (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md. Mirrors Shizuku's delivery.
 */
package com.eko.rcrm.dc.recorder

import android.os.Bundle
import android.os.Process
import android.util.Log

/** Delivers the recorder binder from the privileged shell-uid daemon to the app's exported
 * [RecorderBinderProvider], the same non-app->app mechanism Shizuku uses. Everything hidden-API is
 * reached by reflection so it compiles against the public SDK. */
internal object BinderDelivery {
    private const val TAG = "RCRM:BinderDelivery"
    private const val USER_0 = 0

    fun deliverBinderToApp(binder: android.os.IBinder, authority: String): Boolean {
        val bundle = Bundle().apply {
            putParcelable(RecorderBinderProvider.EXTRA_BINDER, BinderContainer(binder))
        }
        if (runCatching { viaActivityManager(authority, bundle) }
                .onFailure { Log.w(TAG, "getContentProviderExternal path failed: ${it.message}") }
                .getOrDefault(false)) return true
        return runCatching { viaSystemContext(authority, bundle) }
            .onFailure { Log.e(TAG, "system-context path failed: ${it.message}") }
            .getOrDefault(false)
    }

    private fun viaActivityManager(authority: String, bundle: Bundle): Boolean {
        val am = Class.forName("android.app.ActivityManager").getMethod("getService").invoke(null)
            ?: throw IllegalStateException("ActivityManager.getService() null")
        val amClass = am.javaClass
        val gcpe = amClass.methods.first { it.name == "getContentProviderExternal" && it.parameterTypes.size == 4 }
        val holder = gcpe.invoke(am, authority, USER_0, null, authority)
            ?: throw IllegalStateException("getContentProviderExternal null holder")
        try {
            val provider = holder.javaClass.getField("provider").get(holder)
                ?: throw IllegalStateException("holder.provider null")
            return callProvider(provider, authority, bundle) != null
        } finally {
            runCatching {
                amClass.methods.firstOrNull { it.name == "removeContentProviderExternal" && it.parameterTypes.size == 2 }
                    ?.invoke(am, authority, null)
            }
        }
    }

    private fun callProvider(provider: Any, authority: String, bundle: Bundle): Bundle? {
        val cls = provider.javaClass
        buildAttributionSource()?.let { src ->
            cls.methods.firstOrNull {
                it.name == "call" && it.parameterTypes.size == 5 &&
                    it.parameterTypes[0].name == "android.content.AttributionSource"
            }?.let { return it.invoke(provider, src, authority, RecorderBinderProvider.METHOD_SEND_BINDER, null, bundle) as? Bundle }
        }
        cls.methods.firstOrNull { it.name == "call" && it.parameterTypes.size == 6 && it.parameterTypes[0] == String::class.java }
            ?.let { return it.invoke(provider, null, null, authority, RecorderBinderProvider.METHOD_SEND_BINDER, null, bundle) as? Bundle }
        cls.methods.firstOrNull { it.name == "call" && it.parameterTypes.size == 5 && it.parameterTypes[0] == String::class.java }
            ?.let { return it.invoke(provider, null, authority, RecorderBinderProvider.METHOD_SEND_BINDER, null, bundle) as? Bundle }
        throw NoSuchMethodException("No usable IContentProvider.call overload")
    }

    private fun buildAttributionSource(): Any? = runCatching {
        val builderClass = Class.forName("android.content.AttributionSource\$Builder")
        val builder = builderClass.getConstructor(Int::class.javaPrimitiveType).newInstance(Process.myUid())
        builderClass.getMethod("setPackageName", String::class.java).invoke(builder, null)
        builderClass.getMethod("build").invoke(builder)
    }.getOrNull()

    private fun viaSystemContext(authority: String, bundle: Bundle): Boolean {
        val atClass = Class.forName("android.app.ActivityThread")
        val at = atClass.getMethod("systemMain").invoke(null) ?: throw IllegalStateException("systemMain null")
        val ctx = atClass.getMethod("getSystemContext").invoke(at) as? android.content.Context
            ?: throw IllegalStateException("getSystemContext null")
        val uri = android.net.Uri.parse("content://$authority")
        return ctx.contentResolver.call(uri, RecorderBinderProvider.METHOD_SEND_BINDER, null, bundle) != null
    }
}
