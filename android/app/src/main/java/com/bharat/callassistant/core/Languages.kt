package com.bharat.callassistant.core

/** Languages the backend accepts (Gnani Prisma STT and Timbre TTS both support them). */
data class Language(val code: String, val nativeName: String, val englishName: String)

object Languages {
    val supported = listOf(
        Language("kn-IN", "ಕನ್ನಡ", "Kannada"),
        Language("hi-IN", "हिन्दी", "Hindi"),
        Language("en-IN", "English", "English"),
        Language("bn-IN", "বাংলা", "Bengali"),
        Language("pa-IN", "ਪੰਜਾਬੀ", "Punjabi"),
        Language("ta-IN", "தமிழ்", "Tamil"),
        Language("te-IN", "తెలుగు", "Telugu"),
        Language("ml-IN", "മലയാളം", "Malayalam"),
        Language("mr-IN", "मराठी", "Marathi"),
        Language("gu-IN", "ગુજરાતી", "Gujarati"),
    )

    const val DEFAULT = "kn-IN"

    fun nativeName(code: String): String =
        supported.firstOrNull { it.code == code }?.nativeName ?: code
}
