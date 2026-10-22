plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("com.google.dagger.hilt.android")
    id("org.jetbrains.kotlin.kapt")
}

android {
    namespace = "com.eko.rcrm.dc"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.eko.rcrm.dc"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // Default (used by debug): this PC's LAN IP over plain HTTP for phone-on-same-Wi-Fi
        // testing. Cleartext to this host is allowed ONLY in debug builds, via
        // src/debug/res/xml/network_security_config.xml. Release overrides this below with HTTPS.
        buildConfigField("String", "API_BASE_URL", "\"http://192.168.30.25:8010/api/v1/\"")
    }

    buildTypes {
        release {
            // Bank-grade: shrink + obfuscate so the shipped APK doesn't decompile to readable code
            // that exposes the token flow or the CRM-contact recording gate. Keep rules for
            // serialization/Retrofit/Room live in proguard-rules.pro.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // Release must talk to the CRM over HTTPS only (cleartext is forbidden by the release
            // network-security config). Supply the real host at build time, e.g.
            //   ./gradlew assembleRelease -PrcrmApiBaseUrl=https://crm.example.bank/api/v1/
            val releaseApiBaseUrl = (project.findProperty("rcrmApiBaseUrl") as String?)
                ?: "https://REPLACE_WITH_PRODUCTION_HOST/api/v1/"
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiBaseUrl\"")
        }
        debug {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
        // Generated stubs for IRecorderService, the binder the app and the shell-uid recorder
        // process talk over (ported from CallVault / ShizuCallRecorder).
        aidl = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.09.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.6")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.6")
    implementation("androidx.lifecycle:lifecycle-process:2.8.6")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("androidx.navigation:navigation-compose:2.8.0")

    implementation("com.google.dagger:hilt-android:2.52")
    kapt("com.google.dagger:hilt-android-compiler:2.52")
    implementation("androidx.hilt:hilt-navigation-compose:1.2.0")

    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    kapt("androidx.room:room-compiler:2.6.1")

    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.jakewharton.retrofit:retrofit2-kotlinx-serialization-converter:1.0.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.1")

    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("androidx.hilt:hilt-work:1.2.0")
    kapt("androidx.hilt:hilt-compiler:1.2.0")

    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("androidx.documentfile:documentfile:1.0.1")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // Shizuku: one privilege source for the ported CallVault call-audio recorder. Apache-2.0.
    implementation("dev.rikka.shizuku:api:13.1.5")
    implementation("dev.rikka.shizuku:provider:13.1.5")

    // Embedded-ADB privilege source (built-in mode, no second app): pairs with the phone's own
    // Wireless Debugging and runs a shell-uid recorder. libadb-android does the ADB protocol/pairing/TLS.
    implementation("com.github.MuntashirAkon:libadb-android:3.1.1")
    implementation("org.conscrypt:conscrypt-android:2.5.2")
    compileOnly("org.bouncycastle:bcprov-jdk15to18:1.81")

    testImplementation("junit:junit:4.13.2")
}

kapt {
    correctErrorTypes = true
}
