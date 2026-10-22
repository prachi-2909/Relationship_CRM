package com.eko.rcrm.dc

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.work.Configuration
import com.eko.rcrm.dc.data.local.CallAudioStore
import com.eko.rcrm.dc.presence.AppLifecycleObserver
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

@HiltAndroidApp
class RcrmApplication : Application(), Configuration.Provider {

    @Inject
    lateinit var workerFactory: HiltWorkerFactory

    @Inject
    lateinit var appLifecycleObserver: AppLifecycleObserver

    @Inject
    lateinit var callAudioStore: CallAudioStore

    override fun onCreate() {
        super.onCreate()
        ProcessLifecycleOwner.get().lifecycle.addObserver(appLifecycleObserver)
        // Retention backstop: no call audio outlives CallAudioStore.MAX_AGE_MS on the phone.
        Thread { runCatching { callAudioStore.purgeOlderThan() } }.start()
        registerShizuku()
    }

    /** Makes the Shizuku API usable for the privileged two-way recorder. Entirely best-effort: on a
     * phone without Shizuku these listeners simply never fire, and nothing here may crash startup. */
    private fun registerShizuku() {
        runCatching {
            rikka.shizuku.Shizuku.addBinderReceivedListenerSticky {
                // Binder is up; capability checks (pingBinder/checkSelfPermission) now work.
            }
            rikka.shizuku.Shizuku.addBinderDeadListener {
                com.eko.rcrm.dc.recorder.RecorderConnection.onBinderDied()
            }
        }
    }

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()
}
