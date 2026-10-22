package com.eko.rcrm.dc

import android.Manifest
import android.app.KeyguardManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.eko.rcrm.dc.data.local.TokenStore
import com.eko.rcrm.dc.navigation.RcrmNavHost
import com.eko.rcrm.dc.security.AppLockManager
import com.eko.rcrm.dc.security.DeviceIntegrity
import com.eko.rcrm.dc.ui.theme.RcrmTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var appLockManager: AppLockManager
    @Inject lateinit var tokenStore: TokenStore

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { }

    private val unlockLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) appLockManager.markUnlocked()
        }

    override fun onStart() {
        super.onStart()
        appLockManager.onEnterForeground(tokenStore.hasToken())
    }

    override fun onStop() {
        super.onStop()
        appLockManager.onEnterBackground()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Keep CRM screens (official PII, call transcripts) out of screenshots, screen recordings
        // and the Recents thumbnail.
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        enableEdgeToEdge()

        // A bank-grade release refuses to run on a rooted / debugger-attached / debuggable device,
        // where the token and on-device data cannot be protected. Never enforced in debug builds.
        if (DeviceIntegrity.shouldBlock(this)) {
            setContent { RcrmTheme { Surface(modifier = Modifier.fillMaxSize()) { BlockedScreen() } } }
            return
        }

        requestRuntimePermissionsUpfront()
        setContent {
            RcrmTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val locked by appLockManager.locked.collectAsState()
                    if (locked) {
                        LockScreen(onUnlock = ::promptDeviceCredential)
                        LaunchedEffect(Unit) { promptDeviceCredential() }
                    } else {
                        RcrmNavHost()
                    }
                }
            }
        }
    }

    /** Shows the phone's own PIN / pattern / biometric prompt. If the device has no secure lock set,
     * there is nothing to prompt with, so the app unlocks (it cannot invent a credential) - an MDM
     * policy requiring a device passcode is what closes that gap on managed fleets. */
    private fun promptDeviceCredential() {
        val keyguard = getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        if (!keyguard.isDeviceSecure) {
            appLockManager.markUnlocked()
            return
        }
        @Suppress("DEPRECATION")
        val intent = keyguard.createConfirmDeviceCredentialIntent(
            "Unlock SBI CRM", "Confirm your device credential to continue"
        )
        if (intent != null) unlockLauncher.launch(intent) else appLockManager.markUnlocked()
    }

    @androidx.compose.runtime.Composable
    private fun LockScreen(onUnlock: () -> Unit) {
        Column(
            modifier = Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(text = "Locked", style = MaterialTheme.typography.titleLarge)
            Text(
                text = "Confirm your device credential to continue.",
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 12.dp, bottom = 20.dp),
            )
            Button(onClick = onUnlock) { Text("Unlock") }
        }
    }

    @androidx.compose.runtime.Composable
    private fun BlockedScreen() {
        Column(
            modifier = Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = "This app can't run on this device",
                style = MaterialTheme.typography.titleLarge,
                textAlign = TextAlign.Center,
            )
            Text(
                text = "For security, the CRM won't run on a rooted or debug-enabled device. " +
                    "Please use a standard, unmodified phone.",
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 12.dp),
            )
        }
    }

    /** Asks for every dangerous permission this app ever needs right away, instead of
     * piecemeal the first time each feature is used - a DC who denies one mid-task (or just
     * doesn't notice a prompt behind the native dialer, as happened with POST_NOTIFICATIONS
     * going unrequested entirely) ends up with a feature that silently half-works. Already-
     * granted permissions are skipped automatically; the system only prompts for the rest. */
    private fun requestRuntimePermissionsUpfront() {
        val candidates = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            add(Manifest.permission.CALL_PHONE)
            add(Manifest.permission.READ_PHONE_STATE)
            // Lets the call-screening service be notified for calls with saved contacts too.
            add(Manifest.permission.READ_CONTACTS)
            // Confirms whether a call was actually answered (missed/rejected calls aren't logged/recorded).
            add(Manifest.permission.READ_CALL_LOG)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        val missing = candidates.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            permissionLauncher.launch(missing.toTypedArray())
        }
    }
}
