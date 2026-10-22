package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.data.remote.dto.AttestVerifyRequestDto
import com.eko.rcrm.dc.security.KeyAttestationProvider
import javax.inject.Inject
import javax.inject.Singleton

/** Runs Android hardware Key Attestation against the backend after login: fetch a challenge, have
 * the Keystore attest to it, send the chain back for verification. Report-only on the client - it
 * returns the server's verdict for logging but never blocks the DC; enforcement (if any) is the
 * server's decision (settings.require_device_attestation). Safe to call fire-and-forget. */
@Singleton
class DeviceAttestationRepository @Inject constructor(
    private val apiService: ApiService,
    private val keyAttestationProvider: KeyAttestationProvider
) {
    data class Verdict(val attested: Boolean, val enforced: Boolean, val reason: String)

    suspend fun attest(): Verdict? = runCatching {
        val challenge = apiService.attestChallenge().challenge
        val chain = keyAttestationProvider.attestationChain(challenge) ?: return null
        val resp = apiService.attestVerify(AttestVerifyRequestDto(challenge = challenge, certificates = chain))
        Verdict(attested = resp.attested, enforced = resp.enforced, reason = resp.reason)
    }.getOrNull()
}
