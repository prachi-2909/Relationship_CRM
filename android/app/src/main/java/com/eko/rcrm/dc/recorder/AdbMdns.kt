/*
 * Derived from CallVault's AdbMdns (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** mDNS discovery of an ADB wireless service (pairing or connect port). Reports the resolved port. */
class AdbMdns(context: Context, private val serviceType: String, private val onPort: (Int) -> Unit) {
    private var running = false
    private var serviceName: String? = null
    private val listener = DiscoveryListener(this)
    private val nsdManager: NsdManager = context.getSystemService(NsdManager::class.java)

    fun start() {
        if (running) return
        running = true
        runCatching { nsdManager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, listener) }
    }

    fun stop() {
        if (!running) return
        running = false
        runCatching { nsdManager.stopServiceDiscovery(listener) }
    }

    private fun onServiceFound(info: NsdServiceInfo) {
        @Suppress("DEPRECATION")
        runCatching { nsdManager.resolveService(info, ResolveListener(this)) }
    }

    private fun onServiceLost(info: NsdServiceInfo) {
        if (info.serviceName == serviceName) onPort(-1)
    }

    @Suppress("DEPRECATION")
    private fun onServiceResolved(resolved: NsdServiceInfo) {
        if (!running) return
        val port = resolved.port
        if (port > 0) { serviceName = resolved.serviceName; onPort(port) }
    }

    private class DiscoveryListener(private val m: AdbMdns) : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(t: String) {}
        override fun onStartDiscoveryFailed(t: String, e: Int) {}
        override fun onDiscoveryStopped(t: String) {}
        override fun onStopDiscoveryFailed(t: String, e: Int) {}
        override fun onServiceFound(i: NsdServiceInfo) = m.onServiceFound(i)
        override fun onServiceLost(i: NsdServiceInfo) = m.onServiceLost(i)
    }

    @Suppress("DEPRECATION")
    private class ResolveListener(private val m: AdbMdns) : NsdManager.ResolveListener {
        override fun onResolveFailed(i: NsdServiceInfo, e: Int) {}
        override fun onServiceResolved(i: NsdServiceInfo) = m.onServiceResolved(i)
    }

    companion object {
        const val TLS_CONNECT = "_adb-tls-connect._tcp"
        const val TLS_PAIRING = "_adb-tls-pairing._tcp"

        /** Blocks up to [timeoutMs] for a service of [serviceType], returning its port or null. Off-main. */
        fun discoverPort(context: Context, serviceType: String, timeoutMs: Long): Int? {
            val portRef = AtomicInteger(-1)
            val latch = CountDownLatch(1)
            val mdns = AdbMdns(context, serviceType) { p -> if (p > 0) { portRef.set(p); latch.countDown() } }
            mdns.start()
            return try {
                if (latch.await(timeoutMs, TimeUnit.MILLISECONDS)) portRef.get().takeIf { it > 0 } else null
            } finally { mdns.stop() }
        }
    }
}
