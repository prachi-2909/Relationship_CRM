package com.eko.rcrm.dc.data.remote

import com.eko.rcrm.dc.data.remote.dto.CallSessionDetailDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionListResponseDto
import com.eko.rcrm.dc.data.remote.dto.CallSessionSummaryDto
import com.eko.rcrm.dc.data.remote.dto.ConfirmRequestDto
import com.eko.rcrm.dc.data.remote.dto.IdentityCreateRequestDto
import com.eko.rcrm.dc.data.remote.dto.IdentityLinkRequestDto
import com.eko.rcrm.dc.data.remote.dto.LoginRequestDto
import com.eko.rcrm.dc.data.remote.dto.LoginResponseDto
import com.eko.rcrm.dc.data.remote.dto.ManualTextRequestDto
import com.eko.rcrm.dc.data.remote.dto.OfficialListResponseDto
import com.eko.rcrm.dc.data.remote.dto.OutgoingCallRequestDto
import com.eko.rcrm.dc.data.remote.dto.RemindLaterRequestDto
import com.eko.rcrm.dc.data.remote.dto.UserDto
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
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

    @GET("officials")
    suspend fun searchOfficials(
        @Query("q") query: String?,
        @Query("limit") limit: Int = 6
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
        @Part file: MultipartBody.Part
    ): CallSessionDetailDto

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
}
