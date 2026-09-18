package fr.izquierdo.phototheque.appairage

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import fr.izquierdo.phototheque.reseau.ChargeAppairage
import fr.izquierdo.phototheque.reseau.Contrat

object Appairage {
    /** Lit le JSON du QR. Renvoie null sur tout ce qui n'est pas un appairage :
     *  l'utilisateur peut scanner n'importe quel code-barres, et planter serait
     *  la pire des réponses. */
    fun lire(texteDuQr: String): ChargeAppairage? = try {
        Contrat.json.decodeFromString<ChargeAppairage>(texteDuQr)
    } catch (e: Exception) {
        null
    }
}

/**
 * Le jeton est un secret : il ouvre l'envoi de médias sur le NUC. Il est rangé
 * dans les préférences chiffrées d'Android, jamais en clair.
 */
class Coffre(context: Context) {

    private val prefs = EncryptedSharedPreferences.create(
        context,
        "appairage",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    fun enregistrer(charge: ChargeAppairage) = prefs.edit()
        .putString("url", charge.url)
        .putString("token", charge.token)
        .putString("cert", charge.certSha256)
        .apply()

    fun charge(): ChargeAppairage? {
        val url = prefs.getString("url", null) ?: return null
        val token = prefs.getString("token", null) ?: return null
        return ChargeAppairage(url, token, prefs.getString("cert", null))
    }

    /** Appelé sur un 401 : l'appareil a été révoqué, le jeton ne redeviendra
     *  jamais valable. Garder un jeton mort ferait réessayer en boucle. */
    fun oublier() = prefs.edit().clear().apply()
}
