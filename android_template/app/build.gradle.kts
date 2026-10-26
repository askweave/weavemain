// GENESIS PROTECTED FILE — server-controlled, never written by the model.
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Per-build values written by the Genesis server (validated server-side, re-checked here).
val genesisProps = Properties().apply {
    val f = rootProject.file("genesis.properties")
    val src = if (f.exists()) f else rootProject.file("genesis.properties.default")
    src.inputStream().use { load(it) }
}
val genesisAppId: String = genesisProps.getProperty("applicationId")
require(Regex("^[a-z][a-z0-9_]{1,30}(\\.[a-z][a-z0-9_]{1,30}){1,4}$").matches(genesisAppId)) {
    "Invalid applicationId in genesis.properties"
}
val genesisVersionName: String = genesisProps.getProperty("versionName", "1.0")
require(Regex("^[0-9]{1,3}(\\.[0-9]{1,3}){0,2}$").matches(genesisVersionName)) {
    "Invalid versionName in genesis.properties"
}

android {
    namespace = "com.genesis.app"
    compileSdk = 35

    defaultConfig {
        applicationId = genesisAppId
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = genesisVersionName
    }

    buildTypes {
        release {
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
        buildConfig = false
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
}
