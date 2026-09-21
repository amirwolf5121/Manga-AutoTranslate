plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.amirwolf.mangatranslator"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.amirwolf.mangatranslator"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.8"

        ndk {
            // همه معماری‌ها: گوشی جدید (arm64)، گوشی قدیمی ۳۲بیت (v7a)،
            // شبیه‌ساز (x86_64) و x86
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86", "x86_64")
        }
    }

    // یک APK جدا برای هر معماری + یک universal همه‌سازگار
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86", "x86_64")
            isUniversalApk = true
        }
    }

    packaging {
        jniLibs.useLegacyPackaging = false
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}

// سورس موتور (manga.py / manga_app.py) به‌صورت asset داخل APK —
// Kotlin در اجرای اول آن‌ها را روی دیسک کپی می‌کند (بدون نیاز به اینترنت
// و بدون اتکا به loader چاکوپی که سورس خالی برمی‌گرداند)
val engineRoot = rootProject.projectDir.parentFile  // ریشه پروژه (کنار android/)
tasks.register<Copy>("copyEngineSources") {
    from(engineRoot) { include("manga.py", "manga_app.py") }
    into("src/main/assets/engine")
}
tasks.named("preBuild") { dependsOn("copyEngineSources") }

// Chaquopy — پایتون داخل اپ (بدون ترموکس)
// نکته: opencv فقط برای پایتون 3.10 در مخزن چاکوپی بیلد شده → version = "3.10"
chaquopy {
    // مدل‌های سنگین OCR (~۳۱MB) داخل APK نمی‌روند — اپ در اجرای اول خودش
    // به files/rapidocr_models دانلود می‌کند (manga.py مدل‌dir را ست می‌کند)
    sourceSets {
        getByName("main") {
            exclude("rapidocr/models/**")
            exclude("**/__pycache__/**")
        }
    }
    defaultConfig {
        version = "3.10"
        // پایتونِ هاست برای رزولو ریکوایرمنت‌ها — با -PchaquopyBuildPython قابل تغییر
        buildPython = listOf(
            (findProperty("chaquopyBuildPython") as String?) ?: "python3")
        pip {
            // فقط چیزهایی که pip گوشی نمی‌تواند نصب کند (wheel native یا
            // وابستگی لانچر) — بقیه را manga.py در اجرای اول خودش نصب می‌کند
            // (_ensure_all_dependencies): google-genai، openai، arabic-reshaper،
            // python-bidi، beautifulsoup4 و …
            install("numpy==1.26.2")
            install("opencv-python==4.5.1.48")
            install("pillow")
            install("shapely")
            // سخت‌وابسته‌های موتور — manga.py بدون آن‌ها import نمی‌شود
            install("arabic-reshaper")
            install("python-bidi==0.4.2")
            install("pyyaml")
            install("requests")
            install("six")
            install("tqdm")
            install("omegaconf")
            install("colorlog")
        }
    }
}

dependencies {
    // ONNX Runtime اندروید — شیم پایتونی onnxruntime روی این کار می‌کند
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
}
