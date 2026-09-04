import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val releaseSigningProperties = Properties()
val releaseSigningPropertiesFile = rootProject.file("key.properties")
if (releaseSigningPropertiesFile.isFile) {
    releaseSigningPropertiesFile.inputStream().use(releaseSigningProperties::load)
}

fun releaseSigningValue(propertyName: String, environmentName: String): String? =
    providers.gradleProperty(propertyName).orNull
        ?: providers.environmentVariable(environmentName).orNull
        ?: releaseSigningProperties.getProperty(propertyName)

val releaseSigningValues = mapOf(
    "storeFile" to releaseSigningValue("storeFile", "PCIP_ANDROID_KEYSTORE_PATH"),
    "storePassword" to releaseSigningValue("storePassword", "PCIP_ANDROID_KEYSTORE_PASSWORD"),
    "keyAlias" to releaseSigningValue("keyAlias", "PCIP_ANDROID_KEY_ALIAS"),
    "keyPassword" to releaseSigningValue("keyPassword", "PCIP_ANDROID_KEY_PASSWORD"),
)
val releaseSigningConfigured = releaseSigningValues.values.all { !it.isNullOrBlank() }

android {
    namespace = "uk.co.politisltd.citizencentric.participant"
    // Google Play submission policy requires API level 36 from September 2026.
    compileSdk = 36
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "uk.co.politisltd.citizencentric.participant"
        minSdk = 24
        targetSdk = 36
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            if (releaseSigningConfigured) {
                storeFile = file(releaseSigningValues.getValue("storeFile")!!)
                storePassword = releaseSigningValues.getValue("storePassword")
                keyAlias = releaseSigningValues.getValue("keyAlias")
                keyPassword = releaseSigningValues.getValue("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isDebuggable = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    lint {
        // geolocator ships an unused optional background-stream implementation that
        // posts a foreground notification. Citizen Centric uses only one-off
        // getCurrentPosition capture and declares neither notification nor
        // background-location permission; its source-level use is regression-tested.
        disable += "NotificationPermission"
    }
}

tasks.configureEach {
    val isReleasePackagingTask = name.contains("release", ignoreCase = true) &&
        (name.contains("assemble", ignoreCase = true) ||
            name.contains("bundle", ignoreCase = true) ||
            name.contains("sign", ignoreCase = true))
    if (isReleasePackagingTask) {
        doFirst {
            check(releaseSigningConfigured) {
                "Production release signing is not configured. Supply the upload-key values through " +
                    "ignored android/key.properties, Gradle properties, or PCIP_ANDROID_KEYSTORE_* environment variables."
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
