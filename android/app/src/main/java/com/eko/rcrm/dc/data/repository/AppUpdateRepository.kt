package com.eko.rcrm.dc.data.repository

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.content.pm.Signature
import android.os.Build
import com.eko.rcrm.dc.BuildConfig
import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.domain.model.AppVersionInfo
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.util.safeApiCall
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Sideload self-update: checks app/version, downloads app/download's APK into the app's own cache
 * dir, and - before it is ever handed to the installer - verifies the APK is signed by THIS app's
 * own signing key. Without that check a MITM or a compromised backend could serve any APK and have
 * it installed on one tap (install-unknown-apps is already granted). An APK not signed by our key,
 * or for a different package, is rejected and deleted.
 */
@Singleton
class AppUpdateRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val apiService: ApiService,
    private val okHttpClient: OkHttpClient
) {
    suspend fun checkForUpdate(): Result<AppVersionInfo> = safeApiCall {
        val dto = apiService.getAppVersion()
        AppVersionInfo(
            versionCode = dto.version_code,
            versionName = dto.version_name,
            downloadUrl = dto.download_url
        )
    }

    /**
     * [downloadUrl] is a path relative to the server's own origin (scheme+host+port). It is resolved
     * against that origin and the result MUST stay on the same host - otherwise a `download_url` like
     * `@evil.host/x.apk` or `https://evil.host/x.apk` would send the request (and the bearer header the
     * shared client attaches) to an attacker. Redirects are disabled for the same reason.
     */
    suspend fun downloadApk(downloadUrl: String, destination: File): Result<File> = safeApiCall {
        withContext(Dispatchers.IO) {
            val base = BuildConfig.API_BASE_URL.toHttpUrl()
            val origin = "${base.scheme}://${base.host}:${base.port}/".toHttpUrl()
            val resolved = origin.resolve(downloadUrl)
                ?: error("Invalid update URL")
            require(resolved.host == origin.host && resolved.scheme == origin.scheme) {
                "Update URL points off the CRM server; refusing to download it"
            }

            val noRedirectClient = okHttpClient.newBuilder()
                .followRedirects(false)
                .followSslRedirects(false)
                .build()
            val request = Request.Builder().url(resolved).get().build()
            noRedirectClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    error("Download failed: HTTP ${response.code}")
                }
                val body = response.body ?: error("Empty download response")
                body.byteStream().use { input ->
                    FileOutputStream(destination).use { output -> input.copyTo(output) }
                }
            }

            if (!isSignedBySelf(destination)) {
                destination.delete()
                error("Update rejected: it is not signed by this app's own key.")
            }
            destination
        }
    }

    /** True only when [apk] is for this exact package and carries the same signing certificate(s)
     * as the currently installed app - i.e. it was produced by us and not tampered with. */
    private fun isSignedBySelf(apk: File): Boolean = runCatching {
        val pm = context.packageManager
        val apkInfo = pm.getPackageArchiveInfo(apk.absolutePath, signingFlags()) ?: return false
        if (apkInfo.packageName != context.packageName) return false
        val self = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            pm.getPackageInfo(context.packageName, PackageManager.PackageInfoFlags.of(signingFlags().toLong()))
        } else {
            @Suppress("DEPRECATION")
            pm.getPackageInfo(context.packageName, signingFlags())
        }
        val apkCerts = certDigests(apkInfo)
        val selfCerts = certDigests(self)
        apkCerts.isNotEmpty() && apkCerts == selfCerts
    }.getOrDefault(false)

    @Suppress("DEPRECATION")
    private fun signingFlags(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) PackageManager.GET_SIGNING_CERTIFICATES
        else PackageManager.GET_SIGNATURES

    /** SHA-256 of each signing certificate, as a set so order never matters. */
    @Suppress("DEPRECATION")
    private fun certDigests(info: PackageInfo): Set<String> {
        val signatures: Array<Signature> = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val signing = info.signingInfo ?: return emptySet()
            (signing.apkContentsSigners ?: emptyArray())
        } else {
            info.signatures ?: emptyArray()
        }
        val sha = MessageDigest.getInstance("SHA-256")
        return signatures.map { sha.digest(it.toByteArray()).joinToString("") { b -> "%02x".format(b) } }.toSet()
    }
}
