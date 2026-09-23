package com.eko.rcrm.dc.util

import kotlinx.coroutines.CancellationException

/** Simple outcome wrapper used consistently across repositories and ViewModels. */
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val message: String, val throwable: Throwable? = null) : Result<Nothing>()

    inline fun onSuccess(action: (T) -> Unit): Result<T> {
        if (this is Success) action(data)
        return this
    }

    inline fun onError(action: (String) -> Unit): Result<T> {
        if (this is Error) action(message)
        return this
    }
}

suspend fun <T> safeApiCall(block: suspend () -> T): Result<T> {
    return try {
        Result.Success(block())
    } catch (c: CancellationException) {
        throw c
    } catch (t: Throwable) {
        Result.Error(t.message ?: "Something went wrong. Please try again.", t)
    }
}
