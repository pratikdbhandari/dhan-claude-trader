package com.dhanclaude.trader

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.dhanclaude.trader.databinding.ActivitySettingsBinding

/**
 * Lets the user set the trading server's base URL. This is the only thing the
 * app needs configured — the phone must be able to reach the PC running uvicorn
 * (same Wi-Fi via the PC's LAN IP, or a public tunnel URL).
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.serverUrlInput.setText(Prefs.getServerUrl(this))

        binding.saveButton.setOnClickListener {
            val raw = binding.serverUrlInput.text?.toString()?.trim().orEmpty()
            when {
                raw.isEmpty() ->
                    Toast.makeText(this, R.string.err_url_empty, Toast.LENGTH_SHORT).show()
                !raw.startsWith("http://") && !raw.startsWith("https://") ->
                    Toast.makeText(this, R.string.err_url_scheme, Toast.LENGTH_LONG).show()
                else -> {
                    Prefs.setServerUrl(this, raw)
                    Toast.makeText(this, R.string.saved, Toast.LENGTH_SHORT).show()
                    finish()
                }
            }
        }
    }
}
