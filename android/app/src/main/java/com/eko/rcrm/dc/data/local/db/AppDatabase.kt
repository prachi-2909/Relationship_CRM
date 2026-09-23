package com.eko.rcrm.dc.data.local.db

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [PendingUploadEntity::class],
    version = 1,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingUploadDao(): PendingUploadDao

    companion object {
        const val DATABASE_NAME = "rcrm_database"
    }
}
