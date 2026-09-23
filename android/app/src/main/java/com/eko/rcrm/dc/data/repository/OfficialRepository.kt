package com.eko.rcrm.dc.data.repository

import com.eko.rcrm.dc.data.remote.ApiService
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.util.Result
import com.eko.rcrm.dc.util.safeApiCall
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class OfficialRepository @Inject constructor(
    private val apiService: ApiService
) {
    suspend fun search(query: String, limit: Int = 6): Result<List<Official>> = safeApiCall {
        apiService.searchOfficials(query = query.ifBlank { null }, limit = limit)
            .items.map { it.toDomain() }
    }
}
