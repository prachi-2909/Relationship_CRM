package com.eko.rcrm.dc.data.remote

import com.eko.rcrm.dc.data.remote.dto.AppVersionDto
import com.eko.rcrm.dc.data.remote.dto.AttestChallengeDto
import com.eko.rcrm.dc.data.remote.dto.CommitmentDto
import com.eko.rcrm.dc.data.remote.dto.CommitmentStatusRequestDto
import com.eko.rcrm.dc.data.remote.dto.CspDto
import com.eko.rcrm.dc.data.remote.dto.DuplicateDecisionRequestDto
import com.eko.rcrm.dc.data.remote.dto.FeedbackRequestDto
import com.eko.rcrm.dc.data.remote.dto.OfficialBriefingDto
import com.eko.rcrm.dc.data.remote.dto.PreCallDto
import com.eko.rcrm.dc.data.remote.dto.AttestVerifyRequestDto
import com.eko.rcrm.dc.data.remote.dto.AttestVerifyResponseDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionDetailDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionListResponseDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionSummaryDto
import com.eko.rcrm.dc.data.remote.dto.ConfirmRequestDto
import com.eko.rcrm.dc.data.remote.dto.DcProfileDto
import com.eko.rcrm.dc.data.remote.dto.DcTerritoryDto
import com.eko.rcrm.dc.data.remote.dto.CallerLookupRequestDto
import com.eko.rcrm.dc.data.remote.dto.CallerLookupResponseDto
import com.eko.rcrm.dc.data.remote.dto.IdentityCreateRequestDto
import com.eko.rcrm.dc.data.remote.dto.IdentityLinkRequestDto
import com.eko.rcrm.dc.data.remote.dto.IncomingNativeCallRequestDto
import com.eko.rcrm.dc.data.remote.dto.LoginRequestDto
import com.eko.rcrm.dc.data.remote.dto.LoginResponseDto
import com.eko.rcrm.dc.data.remote.dto.ManualTextRequestDto
import com.eko.rcrm.dc.data.remote.dto.NativeCallCompleteRequestDto
import com.eko.rcrm.dc.data.remote.dto.OfficialCreateRequestDto
import com.eko.rcrm.dc.data.remote.dto.OfficialDto
import com.eko.rcrm.dc.data.remote.dto.OfficialListResponseDto
import com.eko.rcrm.dc.data.remote.dto.OfficialUpdateRequestDto
import com.eko.rcrm.dc.data.remote.dto.OutgoingCallRequestDto
import com.eko.rcrm.dc.data.remote.dto.RemindLaterRequestDto
import com.eko.rcrm.dc.data.remote.dto.UserDto
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {

    @POST("auth/login")
    suspend fun login(@Body request: LoginRequestDto): LoginResponseDto

    @GET("auth/me")
    suspend fun me(): UserDto

    @POST("auth/logout")
    suspend fun logout()

    @POST("presence/heartbeat")
    suspend fun presenceHeartbeat()

    @POST("presence/background")
    suspend fun presenceBackground()

    @GET("officials")
    suspend fun searchOfficials(
        @Query("q") query: String?,
        @Query("limit") limit: Int = 100,
        @Query("unit_id") unitId: Int? = null
    ): OfficialListResponseDto

    @POST("calls/outgoing")
    suspend fun startOutgoingCall(@Body request: OutgoingCallRequestDto): CallSessionSummaryDto

    @GET("calls/pending")
    suspend fun getPendingCalls(@Query("limit") limit: Int = 100): CallSessionListResponseDto

    @GET("calls/history")
    suspend fun getCallHistory(@Query("limit") limit: Int = 100): CallSessionListResponseDto

    @GET("calls/{id}")
    suspend fun getCall(@Path("id") id: Int): CallSessionDetailDto

    @POST("calls/{id}/manual-text")
    suspend fun submitManualText(
        @Path("id") id: Int,
        @Body request: ManualTextRequestDto
    ): CallSessionDetailDto

    @Multipart
    @POST("calls/{id}/voice-note")
    suspend fun uploadVoiceNote(
        @Path("id") id: Int,
        @Part file: MultipartBody.Part,
        @Part("kind") kind: RequestBody
    ): CallSessionDetailDto

    @DELETE("calls/{id}/voice-note")
    suspend fun deleteVoiceNote(@Path("id") id: Int): CallSessionDetailDto

    @POST("calls/{id}/identity/link")
    suspend fun linkIdentity(
        @Path("id") id: Int,
        @Body request: IdentityLinkRequestDto
    ): CallSessionSummaryDto

    @POST("calls/{id}/identity/create")
    suspend fun createIdentity(
        @Path("id") id: Int,
        @Body request: IdentityCreateRequestDto
    ): CallSessionSummaryDto

    @POST("calls/{id}/identity/dismiss")
    suspend fun dismissIdentity(@Path("id") id: Int): CallSessionSummaryDto

    @POST("calls/{id}/confirm")
    suspend fun confirmCall(
        @Path("id") id: Int,
        @Body request: ConfirmRequestDto
    ): CallSessionDetailDto

    @POST("calls/{id}/remind-later")
    suspend fun remindLater(
        @Path("id") id: Int,
        @Body request: RemindLaterRequestDto
    ): CallSessionSummaryDto

    @POST("calls/{id}/native/complete")
    suspend fun completeNativeCall(
        @Path("id") id: Int,
        @Body request: NativeCallCompleteRequestDto
    ): CallSessionDetailDto

    @POST("calls/native/incoming")
    suspend fun logNativeCall(@Body request: IncomingNativeCallRequestDto): CallSessionDetailDto

    @POST("calls/lookup")
    suspend fun lookupCaller(@Body request: CallerLookupRequestDto): CallerLookupResponseDto

    @POST("auth/attest/challenge")
    suspend fun attestChallenge(): AttestChallengeDto

    @POST("auth/attest/verify")
    suspend fun attestVerify(@Body request: AttestVerifyRequestDto): AttestVerifyResponseDto

    // ---- DC profile / territory ----

    @GET("dc/profile")
    suspend fun getDcProfile(): DcProfileDto

    @GET("dc-territories")
    suspend fun getDcTerritories(): List<DcTerritoryDto>

    // ---- CSPs: the logged-in RM's own calling list ----

    @GET("csps/mine")
    suspend fun getMyCsps(): List<CspDto>

    // Pre-call intelligence for one of the RM's CSPs - the same briefing the web CRM shows. The server
    // answers 404 for a CSP that is not the caller's, so an id typed in by hand reveals nothing.
    @GET("csps/{id}/pre-call")
    suspend fun getCspPreCall(@Path("id") cspId: Int): PreCallDto

    @POST("csps/commitments/{id}/status")
    suspend fun setCommitmentStatus(
        @Path("id") commitmentId: Int,
        @Body request: CommitmentStatusRequestDto
    ): CommitmentDto

    @POST("csps/commitments/{id}/duplicate")
    suspend fun reviewCspCommitmentDuplicate(
        @Path("id") commitmentId: Int,
        @Body request: DuplicateDecisionRequestDto
    ): CommitmentDto

    @POST("csps/{id}/feedback")
    suspend fun sendCspFeedback(@Path("id") cspId: Int, @Body request: FeedbackRequestDto)

    // ---- SBI-official briefing (DC; the server scopes it to the DC's territory and answers 404 otherwise) ----

    @GET("officials/{id}/intelligence")
    suspend fun getOfficialIntelligence(@Path("id") officialId: Int): OfficialBriefingDto

    @POST("officials/commitments/{id}/status")
    suspend fun setOfficialCommitmentStatus(
        @Path("id") commitmentId: Int,
        @Body request: CommitmentStatusRequestDto
    ): CommitmentDto

    @POST("officials/commitments/{id}/duplicate")
    suspend fun reviewOfficialCommitmentDuplicate(
        @Path("id") commitmentId: Int,
        @Body request: DuplicateDecisionRequestDto
    ): CommitmentDto

    @POST("officials/{id}/feedback")
    suspend fun sendOfficialFeedback(@Path("id") officialId: Int, @Body request: FeedbackRequestDto)

    // ---- App self-update ----

    @GET("app/version")
    suspend fun getAppVersion(): AppVersionDto

    // ---- Officials: read/create/edit (DC, scoped server-side to their territory) ----

    @GET("officials/{id}")
    suspend fun getOfficial(@Path("id") id: Int): OfficialDto

    @POST("officials")
    suspend fun createOfficial(@Body request: OfficialCreateRequestDto): OfficialDto

    @PATCH("officials/{id}")
    suspend fun updateOfficial(
        @Path("id") id: Int,
        @Body request: OfficialUpdateRequestDto
    ): OfficialDto
}
