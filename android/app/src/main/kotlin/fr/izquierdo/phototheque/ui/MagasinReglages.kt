package fr.izquierdo.phototheque.ui

import android.content.Context

/**
 * Persistance des réglages.
 *
 * Des préférences ordinaires, pas le coffre chiffré : une liste de dossiers
 * n'est pas un secret, et la chiffrer exposerait ce réglage à la panne de
 * Keystore décrite dans `Coffre`. Toute la logique est dans [Reglages], qui se
 * teste sur la JVM ; cette classe ne fait que lire et écrire une chaîne.
 */
class MagasinReglages(context: Context) {

    private val prefs = context.getSharedPreferences("reglages", Context.MODE_PRIVATE)

    fun lire(): Reglages = Reglages.depuisJson(prefs.getString(CLE, null))

    fun ecrire(reglages: Reglages) {
        prefs.edit().putString(CLE, reglages.versJson()).apply()
    }

    private companion object { const val CLE = "reglages" }
}
