package com.eko.rcrm.dc.di

import android.content.Context
import androidx.work.WorkManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * TokenStore, the repositories and the OkHttp/Retrofit pieces all use @Inject constructors
 * directly, so this module only needs to provide framework singletons that don't have one
 * (WorkManager's instance is obtained via a static accessor rather than a constructor).
 */
@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideWorkManager(@ApplicationContext context: Context): WorkManager =
        WorkManager.getInstance(context)
}
