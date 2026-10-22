package com.eko.rcrm.dc.nativecall.recording

import com.eko.rcrm.dc.data.local.TokenStore
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.util.Result
import kotlinx.coroutines.withTimeoutOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** The strict rule every recording must pass before any [RecordingEngine] is started: the DC is
 * logged in to this app, and the other party's number belongs to an active CRM official in the
 * DC's territory (the server's own lookup, which applies the same test again before it accepts a
 * recording - see assert_call_recording_allowed). Anything uncertain - offline, a slow lookup, no
 * number - is a refusal: the call is never recorded on a guess. */
@Singleton
class CrmRecordingGate @Inject constructor(
    private val tokenStore: TokenStore,
    private val callRepository: CallRepository
) {
    sealed interface Decision {
        data object Allowed : Decision
        data class Denied(val reason: String) : Decision
    }

    fun isLoggedIn(): Boolean = tokenStore.hasToken()

    suspend fun check(phone: String?): Decision {
        if (!isLoggedIn()) return Decision.Denied("Not logged in to the CRM app - calls are only recorded while you are logged in.")
        if (phone.isNullOrBlank()) return Decision.Denied("The call's number is unknown, so it can't be checked against the CRM.")
        return when (val lookup = withTimeoutOrNull(LOOKUP_TIMEOUT_MS) { callRepository.isCrmContact(phone) }) {
            null -> Decision.Denied("Couldn't confirm in time that this number is a CRM contact - not recorded.")
            is Result.Error -> Decision.Denied("Couldn't check this number against the CRM (${lookup.message}) - not recorded.")
            is Result.Success ->
                if (lookup.data) Decision.Allowed
                else Decision.Denied("Not a CRM contact in your territory - only calls with CRM officials are recorded.")
        }
    }

    private companion object {
        const val LOOKUP_TIMEOUT_MS = 8_000L
    }
}
