package com.eko.rcrm.dc.security

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.cert.X509Certificate
import javax.inject.Inject
import javax.inject.Singleton

/** Produces an Android hardware Key Attestation chain for a server-issued challenge. The Keystore
 * generates a key in the TEE/StrongBox and returns a certificate chain whose leaf embeds the
 * challenge and the device's verified-boot state; the backend verifies it roots in Google's
 * attestation root (see backend app/security/key_attestation.py). Lets a sideloaded / non-Google-Play
 * build prove device integrity without Play Integrity. */
@Singleton
class KeyAttestationProvider @Inject constructor() {

    /** The leaf-first certificate chain as base64 DER strings, or null when the device/key can't
     * attest (older OEM, no hardware attestation) - the caller treats null as "unverified", never a
     * crash. [challengeB64] is the base64 challenge from the backend. */
    fun attestationChain(challengeB64: String): List<String>? = runCatching {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return null
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        runCatching { keyStore.deleteEntry(ALIAS) }

        val challenge = Base64.decode(challengeB64, Base64.NO_WRAP)
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("secp256r1"))
            .setAttestationChallenge(challenge)
            .build()

        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE).apply {
            initialize(spec)
            generateKeyPair()
        }

        val chain = keyStore.getCertificateChain(ALIAS) ?: return null
        chain.filterIsInstance<X509Certificate>()
            .map { Base64.encodeToString(it.encoded, Base64.NO_WRAP) }
            .takeIf { it.isNotEmpty() }
    }.getOrNull()

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "rcrm_device_attestation"
    }
}
