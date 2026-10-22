package com.eko.rcrm.dc.data.local.db

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [PendingUploadEntity::class, ArmedNativeCallEntity::class],
    version = 2,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingUploadDao(): PendingUploadDao
    abstract fun armedNativeCallDao(): ArmedNativeCallDao

    companion object {
        const val DATABASE_NAME = "rcrm_database"
    }
}
