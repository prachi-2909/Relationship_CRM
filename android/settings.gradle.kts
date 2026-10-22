pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // libadb-android (embedded-ADB call recorder, ported from CallVault) is published on JitPack.
        maven { url = uri("https://jitpack.io") }
    }
}

rootProject.name = "sbi-rcrm-dc"
include(":app")
