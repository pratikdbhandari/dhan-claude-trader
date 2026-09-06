package com.dhanclaude.trader

import android.content.Context

/**
 * One place for the single piece of state this app keeps: the base URL of the
 * user's trading server (e.g. http://192.168.1.20:8501 on the LAN, or an https
 * tunnel URL). Landing path (/live) is appended when loading.
 */
object Prefs {
    private const val FILE = "dhan_trader_prefs"
    private const val KEY_SERVER_URL = "server_url"

    fun getServerUrl(ctx: Context): String =
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getString(KEY_SERVER_URL, "")
            .orEmpty()

    fun setServerUrl(ctx: Context, url: String) {
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_SERVER_URL, url.trim().trimEnd('/'))
            .apply()
    }

    fun hasServerUrl(ctx: Context): Boolean = getServerUrl(ctx).isNotEmpty()

    /** Base URL + the app's landing page. */
    fun landingUrl(ctx: Context): String = getServerUrl(ctx) + "/live"
}
