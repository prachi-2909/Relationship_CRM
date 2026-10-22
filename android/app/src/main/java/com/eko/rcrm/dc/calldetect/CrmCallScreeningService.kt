package com.eko.rcrm.dc.calldetect

import android.telecom.Call
import android.telecom.CallScreeningService

/** Only here to learn the phone number of calls made/received on this phone: holding the
 * call-screening role is the one call-log-free way Android gives an app a call's number.
 * It never blocks, silences or alters a call - every call is allowed straight through
 * unchanged. Matching the number against the CRM happens later, off this callback, since
 * the system gives screening services only a few seconds to answer. */
class CrmCallScreeningService : CallScreeningService() {

    override fun onScreenCall(callDetails: Call.Details) {
        try {
            val number = callDetails.handle?.schemeSpecificPart
            CallDetectionStore(applicationContext).recordScreened(number)
        } catch (_: Throwable) {
            // Never let bookkeeping get in the way of the call itself.
        }
        respondToCall(callDetails, CallResponse.Builder().build())
    }
}
