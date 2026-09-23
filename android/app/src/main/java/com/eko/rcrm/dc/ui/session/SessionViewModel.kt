package com.eko.rcrm.dc.ui.session

import androidx.lifecycle.ViewModel
import com.eko.rcrm.dc.data.remote.SessionEventBus
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

/** Thin Activity-scoped bridge so Compose navigation can observe SessionEventBus. */
@HiltViewModel
class SessionViewModel @Inject constructor(
    sessionEventBus: SessionEventBus
) : ViewModel() {
    val sessionExpired = sessionEventBus.sessionExpired
}
