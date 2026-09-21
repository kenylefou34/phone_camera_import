package fr.izquierdo.phototheque.appairage

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import fr.izquierdo.phototheque.reseau.ChargeAppairage
import fr.izquierdo.phototheque.reseau.Contrat

object Appairage {
    /**
     * Lit le JSON du QR. Renvoie null sur tout ce qui n'est pas un appairage :
     * l'utilisateur peut scanner n'importe quel code-barres — etiquette de
     * colis, ticket de caisse, QR publicitaire — et planter serait la pire des
     * reponses.
     *
     * On attrape Exception et non Throwable, deliberement. Attraper une
     * OutOfMemoryError ou une StackOverflowError puis continuer laisserait
     * l'application dans un etat indetermine : le remede serait pire que le
     * mal. Et le risque a ete mesure comme inexistant ici — verifie le
     * 18/09/2026 avec une pile de 512 Ko et une imbrication de 500 000
     * niveaux : le saut des cles inconnues de kotlinx 1.6.3 est ITERATIF, pas
     * recursif, et un QR physiquement scannable plafonne vers 2000 niveaux.
     * Ne « corrigez » donc pas ce catch dans un sens ou dans l'autre sans
     * refaire cette mesure.
     */
    fun lire(texteDuQr: String): ChargeAppairage? = try {
        Contrat.json.decodeFromString<ChargeAppairage>(texteDuQr)
    } catch (_: Exception) {
        null
    }
}

/**
 * Le jeton est un secret : il ouvre l'envoi de médias sur le NUC. Il est rangé
 * dans les préférences chiffrées d'Android, jamais en clair.
 */
class Coffre(context: Context) {

    /**
     * `null` si le coffre n'a pas pu être ouvert du tout. Voir [ouvrir].
     *
     * L'application se comporte alors comme une installation neuve : elle
     * demande un nouvel appairage à chaque lancement. C'est visiblement gênant,
     * donc réparable par l'utilisateur — là où lever fermait l'application au
     * démarrage, sans autre issue que la désinstallation.
     */
    private val prefs: SharedPreferences? = ouvrir(context)

    fun enregistrer(charge: ChargeAppairage) {
        prefs?.edit()
            ?.putString("url", charge.url)
            ?.putString("token", charge.token)
            ?.putString("cert", charge.certSha256)
            ?.apply()
    }

    fun charge(): ChargeAppairage? {
        val p = prefs ?: return null
        val url = p.getString("url", null) ?: return null
        val token = p.getString("token", null) ?: return null
        return ChargeAppairage(url, token, p.getString("cert", null))
    }

    /** Appelé sur un 401 : l'appareil a été révoqué, le jeton ne redeviendra
     *  jamais valable. Garder un jeton mort ferait réessayer en boucle. */
    fun oublier() {
        prefs?.edit()?.clear()?.apply()
    }

    private companion object {
        const val FICHIER = "appairage"

        /**
         * Ouvre les préférences chiffrées, et survit à une clé perdue.
         *
         * `EncryptedSharedPreferences.create` LÈVE quand le fichier chiffré
         * existe mais que la clé du Keystore, elle, a disparu — restauration
         * d'une sauvegarde sur un autre téléphone, Keystore réinitialisé après
         * un changement de code de déverrouillage, mise à jour système ratée.
         * Depuis un initialiseur de champ de ViewModel, cela fermait
         * l'application à CHAQUE lancement, définitivement.
         *
         * Un fichier qu'on ne sait plus déchiffrer ne vaut rien : on l'efface
         * et on repart d'un appairage vierge. Si même cela échoue, on rend
         * `null` plutôt que de lever.
         */
        fun ouvrir(context: Context): SharedPreferences? = try {
            creer(context)
        } catch (e: Exception) {
            runCatching { context.deleteSharedPreferences(FICHIER) }
            runCatching { creer(context) }.getOrNull()
        }

        fun creer(context: Context): SharedPreferences =
            EncryptedSharedPreferences.create(
                context,
                FICHIER,
                MasterKey.Builder(context)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
    }
}
