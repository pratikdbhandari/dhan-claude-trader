package com.dhanclaude.trader

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import com.dhanclaude.trader.databinding.ActivityMainBinding

/**
 * Hosts a single WebView pointed at the user's trading server. If no server URL
 * is configured yet, it bounces to SettingsActivity first. Everything else the
 * user sees is the existing web UI rendered inside the WebView.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val webView: WebView get() = binding.webView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        with(webView.settings) {
            javaScriptEnabled = true          // htmx + the charting JS need this
            domStorageEnabled = true          // localStorage used by the web UI
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = true
            displayZoomControls = false
            databaseEnabled = true
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView, request: WebResourceRequest,
            ): Boolean = false // keep navigation inside the WebView

            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                binding.swipeRefresh.isRefreshing = true
            }

            override fun onPageFinished(view: WebView, url: String?) {
                binding.swipeRefresh.isRefreshing = false
            }

            override fun onReceivedError(
                view: WebView, request: WebResourceRequest, error: WebResourceError,
            ) {
                if (request.isForMainFrame) {
                    binding.swipeRefresh.isRefreshing = false
                    Toast.makeText(
                        this@MainActivity,
                        getString(R.string.err_load, error.description),
                        Toast.LENGTH_LONG,
                    ).show()
                }
            }
        }
        webView.webChromeClient = WebChromeClient()

        binding.swipeRefresh.setOnRefreshListener { webView.reload() }

        // Back button walks WebView history before leaving the app.
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })
    }

    override fun onResume() {
        super.onResume()
        if (!Prefs.hasServerUrl(this)) {
            startActivity(Intent(this, SettingsActivity::class.java))
        } else if (webView.url == null) {
            webView.loadUrl(Prefs.landingUrl(this))
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_refresh -> { webView.reload(); true }
        R.id.action_home -> { webView.loadUrl(Prefs.landingUrl(this)); true }
        R.id.action_settings -> {
            startActivity(Intent(this, SettingsActivity::class.java)); true
        }
        else -> super.onOptionsItemSelected(item)
    }
}
