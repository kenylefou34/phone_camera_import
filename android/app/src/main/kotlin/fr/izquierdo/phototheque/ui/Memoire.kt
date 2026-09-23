package fr.izquierdo.phototheque.ui

import android.content.Context

/**
 * Retient la date de la dernière synchronisation RÉUSSIE, d'un lancement à
 * l'autre.
 *
 * Sans persistance, le compteur de jours repartirait de zéro à chaque fois
 * qu'Android tue l'application — c'est-à-dire en permanence, une application de
 * fond ne survivant que quelques minutes. L'accueil afficherait « Jamais
 * sauvegardé » en rouge après une synchro parfaite, et une alerte toujours
 * allumée est une alerte qu'on apprend à ignorer. Or ce compteur est le SEUL
 * filet contre les pannes où rien ne se passe.
 *
 * De simples préférences ordinaires, pas le coffre chiffré : une date de
 * sauvegarde n'est pas un secret, et la chiffrer ferait courir à ce compteur le
 * risque de panne du Keystore décrit dans Coffre.
 */
class Memoire(context: Context) {

    private val prefs = context.getSharedPreferences("synchro", Context.MODE_PRIVATE)

    fun derniereReussiteMs(): Long? = instantOuJamais(prefs.getLong(CLE, 0L))

    fun enregistrerReussite(instantMs: Long) {
        prefs.edit().putLong(CLE, instantMs).apply()
    }

    /**
     * Efface la dernière réussite connue.
     *
     * Appelée au désappairage : après un changement de serveur, une ancienne
     * réussite ne dit plus rien sur CELUI-CI. L'afficher en vert serait une
     * fausse réassurance — pire qu'une fausse alerte, puisqu'elle éteindrait
     * le seul filet de ce projet contre les pannes muettes.
     */
    fun oublier() {
        prefs.edit().remove(CLE).apply()
    }

    companion object {
        private const val CLE = "derniere_reussite"

        /**
         * Traduit la valeur brute des préférences en « instant, ou jamais ».
         *
         * `getLong` rend 0 quand la clé n'existe pas. Rendre ce 0 tel quel
         * ferait comprendre « sauvegardé le 1er janvier 1970 » : l'accueil
         * afficherait un nombre de jours absurde au lieu du franc « Jamais
         * sauvegardé » qui doit accueillir une installation neuve.
         */
        fun instantOuJamais(brut: Long): Long? = brut.takeIf { it > 0L }
    }
}
