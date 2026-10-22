package com.eko.rcrm.dc.data.local.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction

@Dao
interface ArmedNativeCallDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entity: ArmedNativeCallEntity)

    @Query("DELETE FROM armed_native_calls")
    suspend fun clear()

    /** Single-flight: wipes any stale row before arming the new one - only one call can ever
     * be in flight at a time. */
    @Transaction
    suspend fun arm(entity: ArmedNativeCallEntity) {
        clear()
        insert(entity)
    }

    @Query("SELECT * FROM armed_native_calls LIMIT 1")
    suspend fun current(): ArmedNativeCallEntity?

    @Query("UPDATE armed_native_calls SET state = :state WHERE callSessionId = :callSessionId")
    suspend fun updateState(callSessionId: Int, state: String)
}
