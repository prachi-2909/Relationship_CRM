package com.eko.rcrm.dc.nativecall

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import kotlinx.coroutines.launch

/** Returns a function that, given a [NativeCallRequest], requests CALL_PHONE/READ_PHONE_STATE
 * if needed (same rememberLauncherForActivityResult pattern already used for RECORD_AUDIO in
 * VoiceNoteRecordingScreen) and then places the call via ACTION_CALL - the one spot in the app
 * that does. [onPermissionDenied] lets the caller show an error; the backend-created call
 * session is left as-is either way, so the DC can still log it manually from Call Review. */
@Composable
fun rememberNativeCallLauncher(onPermissionDenied: () -> Unit): (NativeCallRequest) -> Unit {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val launcherViewModel: NativeCallLauncherViewModel = hiltViewModel()
    var pending by remember { mutableStateOf<NativeCallRequest?>(null) }

    fun placeCall(request: NativeCallRequest) {
        launcherViewModel.arm(request.callSessionId, request.phone)
        scope.launch {
            // Foreground-service-start eligibility is tied to this app's own foreground
            // state - start it BEFORE handing focus away via ACTION_CALL, not after. Once
            // the dialer takes over, this app backgrounds immediately, and a service start
            // issued a moment too late can be rejected outright on some OS versions.
            try {
                ContextCompat.startForegroundService(
                    context,
                    NativeCallForegroundService.intent(context, request.callSessionId, request.phone)
                )
            } catch (t: Throwable) {
                // Duration/notification tracking is a nice-to-have next to the call itself
                // actually connecting - never let a platform-specific FGS restriction here
                // crash the app and abort the call the DC is about to place.
                // TEMPORARY diagnostic while we don't have logcat access - remove once native
                // calling is verified working end to end.
                showNativeCallDiagnostic(context, "Call tracking service failed to start", t)
            }
            try {
                context.startActivity(Intent(Intent.ACTION_CALL, Uri.parse("tel:${request.phone}")))
            } catch (t: Throwable) {
                // The dialer never opened, so no call will happen: stop the tracking service and cancel the
                // session rather than leave a call that never took place in Pending / History.
                context.stopService(Intent(context, NativeCallForegroundService::class.java))
                launcherViewModel.cancel(request.callSessionId)
                showNativeCallDiagnostic(context, "Could not open the dialer", t)
            }
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        val request = pending
        pending = null
        // POST_NOTIFICATIONS is best-effort (visibility only) - CALL_PHONE/READ_PHONE_STATE
        // are the only two the call itself actually depends on.
        val essentialGranted = results[Manifest.permission.CALL_PHONE] == true &&
            results[Manifest.permission.READ_PHONE_STATE] == true
        if (request != null && essentialGranted) {
            placeCall(request)
        } else {
            // No permission, so no call: cancel the session that was registered when Call was tapped.
            request?.let { launcherViewModel.cancel(it.callSessionId) }
            onPermissionDenied()
        }
    }

    return { request ->
        val required = buildList {
            add(Manifest.permission.CALL_PHONE)
            add(Manifest.permission.READ_PHONE_STATE)
            // Without this, startForeground()'s notification (and our own diagnostics) are
            // silently suppressed on Android 13+ - not an error, just invisible.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        val allGranted = required.all {
            ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
        }
        if (allGranted) {
            placeCall(request)
        } else {
            pending = request
            permissionLauncher.launch(required.toTypedArray())
        }
    }
}
