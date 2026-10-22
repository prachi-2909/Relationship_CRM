package com.eko.rcrm.dc.nativecall

/** Emitted by a call-placing ViewModel when /calls/outgoing responds with
 * channel="android_native" - the backend didn't place the call, so this device must. */
data class NativeCallRequest(val callSessionId: Int, val phone: String)
