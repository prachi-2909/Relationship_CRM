package com.eko.rcrm.dc.di

import android.content.Context
import androidx.room.Room
import com.eko.rcrm.dc.data.local.db.AppDatabase
import com.eko.rcrm.dc.data.local.db.ArmedNativeCallDao
import com.eko.rcrm.dc.data.local.db.PendingUploadDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideAppDatabase(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, AppDatabase.DATABASE_NAME)
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    @Singleton
    fun providePendingUploadDao(database: AppDatabase): PendingUploadDao = database.pendingUploadDao()

    @Provides
    @Singleton
    fun provideArmedNativeCallDao(database: AppDatabase): ArmedNativeCallDao = database.armedNativeCallDao()
}
