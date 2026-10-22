# Project ProGuard / R8 rules for the release (minified, shrunk) build.

-keepattributes *Annotation*, Signature, InnerClasses, EnclosingMethod

# ---- kotlinx.serialization -------------------------------------------------
# Keep every @Serializable model AND its generated $$serializer, or JSON decoding
# fails at runtime with a stripped serializer. Covers all DTOs and domain models.
-keepattributes RuntimeVisibleAnnotations, AnnotationDefault
-keep,includedescriptorclasses class com.eko.rcrm.dc.**$$serializer { *; }
-keepclassmembers class com.eko.rcrm.dc.** {
    *** Companion;
}
-keepclasseswithmembers class com.eko.rcrm.dc.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep class com.eko.rcrm.dc.data.remote.dto.** { *; }
-keep class com.eko.rcrm.dc.domain.model.** { *; }
-keepclassmembers class kotlinx.serialization.json.** { *; }
-keep,includedescriptorclasses class kotlinx.serialization.** { *; }

# ---- Retrofit / OkHttp -----------------------------------------------------
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class retrofit2.Response
-keepattributes RuntimeVisibleParameterAnnotations, RuntimeVisibleTypeAnnotations
-keep interface com.eko.rcrm.dc.data.remote.ApiService { *; }
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn retrofit2.**

# ---- Room ------------------------------------------------------------------
-keep class * extends androidx.room.RoomDatabase { *; }
-keep @androidx.room.Entity class * { *; }
-dontwarn androidx.room.paging.**

# ---- Hilt / Dagger (generated code is already kept by the plugin) -----------
-dontwarn com.google.errorprone.annotations.**

# ---- Ported call recorder (Shizuku + embedded ADB) -------------------------
# Shizuku instantiates RecorderUserService by name, the embedded-ADB daemon's RecorderServer is
# invoked by name via app_process, the AIDL stub + reflective AudioRecord bypass must survive
# shrinking, and the ADB/TLS libraries are reflection-heavy. Keep them all.
-keep class com.eko.rcrm.dc.recorder.** { *; }
-keep class rikka.shizuku.** { *; }
-keep interface rikka.shizuku.** { *; }
-dontwarn rikka.shizuku.**
-keep class io.github.muntashirakon.adb.** { *; }
-dontwarn io.github.muntashirakon.adb.**
-keep class org.conscrypt.** { *; }
-dontwarn org.conscrypt.**
-keep class org.bouncycastle.** { *; }
-dontwarn org.bouncycastle.**
