/*
 * Derived from CallVault's AdbConnectionManager (a fork of ShizuCallRecorder,
 * Copyright (C) kitsumed (Med)), GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 */
package com.eko.rcrm.dc.recorder

import android.content.Context
import android.os.Build
import android.util.Base64
import io.github.muntashirakon.adb.AbsAdbConnectionManager
import org.bouncycastle.asn1.x509.X509Name
import org.bouncycastle.x509.X509V3CertificateGenerator
import java.io.File
import java.math.BigInteger
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.cert.Certificate
import java.security.cert.CertificateFactory
import java.security.spec.PKCS8EncodedKeySpec
import java.util.Date
import java.util.concurrent.TimeUnit

/** Persisted RSA identity (key + self-signed cert) for the app's embedded ADB client, stored in
 * filesDir so adbd recognises the same client across restarts. Backed by libadb-android. */
class AdbConnectionManager private constructor(context: Context) : AbsAdbConnectionManager() {

    private val privateKey: PrivateKey
    private val certificate: Certificate

    init {
        setApi(Build.VERSION.SDK_INT)
        setTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        val app = context.applicationContext
        val loadedKey = loadPrivateKey(app)
        val loadedCert = loadCertificate(app)
        if (loadedKey != null && loadedCert != null) {
            privateKey = loadedKey; certificate = loadedCert
        } else {
            val (k, c) = generate(app); privateKey = k; certificate = c
        }
    }

    override fun getPrivateKey(): PrivateKey = privateKey
    override fun getCertificate(): Certificate = certificate
    override fun getDeviceName(): String = DEVICE_NAME

    companion object {
        private const val DEVICE_NAME = "SBI-CRM"
        private const val CONNECT_TIMEOUT_SECONDS = 20L
        private const val PRIVATE_KEY_FILE = "adbkey"
        private const val CERTIFICATE_FILE = "adbkey.pem"
        private const val CERT_SUBJECT = "CN=SBI-CRM"
        private const val CERT_ALGO = "SHA512withRSA"
        private const val CERT_VALIDITY_MS = 10L * 365 * 24 * 60 * 60 * 1000

        @Volatile private var instance: AdbConnectionManager? = null

        fun getInstance(context: Context): AdbConnectionManager =
            instance ?: synchronized(this) {
                instance ?: AdbConnectionManager(context.applicationContext).also { instance = it }
            }

        private fun loadPrivateKey(context: Context): PrivateKey? {
            val file = File(context.filesDir, PRIVATE_KEY_FILE)
            if (!file.exists()) return null
            return runCatching {
                KeyFactory.getInstance("RSA").generatePrivate(PKCS8EncodedKeySpec(file.readBytes()))
            }.getOrNull()
        }

        private fun loadCertificate(context: Context): Certificate? {
            val file = File(context.filesDir, CERTIFICATE_FILE)
            if (!file.exists()) return null
            return runCatching {
                file.inputStream().use { CertificateFactory.getInstance("X.509").generateCertificate(it) }
            }.getOrNull()
        }

        @Suppress("DEPRECATION")
        private fun generate(context: Context): Pair<PrivateKey, Certificate> {
            File(context.filesDir, PRIVATE_KEY_FILE).delete()
            File(context.filesDir, CERTIFICATE_FILE).delete()
            val rnd = SecureRandom()
            val kpg = KeyPairGenerator.getInstance("RSA").apply { initialize(2048, rnd) }
            val kp = kpg.generateKeyPair()
            val now = Date()
            val dn = X509Name(CERT_SUBJECT)
            val certGen = X509V3CertificateGenerator().apply {
                setSerialNumber(BigInteger.valueOf(rnd.nextLong() and Long.MAX_VALUE))
                setIssuerDN(dn); setSubjectDN(dn)
                setNotBefore(now); setNotAfter(Date(System.currentTimeMillis() + CERT_VALIDITY_MS))
                setPublicKey(kp.public); setSignatureAlgorithm(CERT_ALGO)
            }
            val cert = certGen.generate(kp.private)
            File(context.filesDir, PRIVATE_KEY_FILE).outputStream().use { it.write(kp.private.encoded) }
            File(context.filesDir, CERTIFICATE_FILE).outputStream().use { os ->
                os.write("-----BEGIN CERTIFICATE-----\n".toByteArray())
                os.write(Base64.encodeToString(cert.encoded, Base64.DEFAULT).toByteArray())
                os.write("-----END CERTIFICATE-----\n".toByteArray())
            }
            return kp.private to cert
        }
    }
}
