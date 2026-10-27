package com.eko.rcrm.dc.navigation

object Routes {
    const val LOGIN = "login"
    const val HOME = "home"
    const val OFFICIAL_SEARCH = "official_search"
    // Pending review and past calls live together on one Calls screen (two tabs).
    const val CALLS = "calls"
    const val PROFILE = "profile"
    const val MANUAL_DIAL = "manual_dial"
    const val MANUAL_LOG = "manual_log"
    const val RECORDING_CAPABILITY = "recording_capability"
    const val MY_CSPS = "my_csps"

    // "Before you call": the pre-call briefing for one CSP (arg = the CSP's primary key).
    const val PRE_CALL_ARG = "cspPk"
    const val PRE_CALL = "pre_call/{$PRE_CALL_ARG}"
    fun preCall(cspPk: Int) = "pre_call/$cspPk"

    // unitId absent (default -1) means "all officials in my territory".
    const val OFFICIAL_LIST_UNIT_ID_ARG = "unitId"
    const val OFFICIAL_LIST_UNIT_NAME_ARG = "unitName"
    const val OFFICIAL_LIST =
        "official_list?$OFFICIAL_LIST_UNIT_ID_ARG={$OFFICIAL_LIST_UNIT_ID_ARG}&$OFFICIAL_LIST_UNIT_NAME_ARG={$OFFICIAL_LIST_UNIT_NAME_ARG}"

    const val CALL_REVIEW_ARG = "callSessionId"
    const val CALL_REVIEW = "call_review/{$CALL_REVIEW_ARG}"
    const val VOICE_NOTE_RECORDING = "voice_note_recording/{$CALL_REVIEW_ARG}"
    const val MANUAL_TEXT_ENTRY = "manual_text_entry/{$CALL_REVIEW_ARG}"

    const val OFFICIAL_DETAIL_ARG = "officialId"
    const val OFFICIAL_DETAIL = "official_detail/{$OFFICIAL_DETAIL_ARG}"

    // officialId is optional here: absent (default -1) means "create new".
    const val OFFICIAL_EDIT_ARG = "officialId"
    const val OFFICIAL_EDIT = "official_edit?$OFFICIAL_EDIT_ARG={$OFFICIAL_EDIT_ARG}"

    fun callReview(callSessionId: Int) = "call_review/$callSessionId"
    fun voiceNoteRecording(callSessionId: Int) = "voice_note_recording/$callSessionId"
    fun manualTextEntry(callSessionId: Int) = "manual_text_entry/$callSessionId"
    fun officialDetail(officialId: Int) = "official_detail/$officialId"
    fun officialCreate() = "official_edit"
    fun officialEdit(officialId: Int) = "official_edit?$OFFICIAL_EDIT_ARG=$officialId"

    fun allOfficials() = "official_list"
    fun officialsForUnit(unitId: Int, unitName: String) =
        "official_list?$OFFICIAL_LIST_UNIT_ID_ARG=$unitId&$OFFICIAL_LIST_UNIT_NAME_ARG=${java.net.URLEncoder.encode(unitName, "UTF-8")}"
}
