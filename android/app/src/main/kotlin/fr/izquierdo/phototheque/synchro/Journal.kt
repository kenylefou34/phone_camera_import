package fr.izquierdo.phototheque.synchro

import android.util.Log

/**
 * Ce que la synchronisation écrit dans le journal Android (`adb logcat`).
 *
 * Constat C2 de la recette du 24/09 : l'application n'y écrivait RIEN. Une
 * passe automatique — lancée par Android, écran éteint, en pleine nuit — ne
 * laissait donc aucune trace de ce qu'elle avait fait. Le seul moyen de le
 * savoir était de reconstituer l'histoire depuis la base interne de
 * WorkManager ; c'est ainsi qu'a été repéré le verrou qui avalait les
 * lancements en silence (constat C1).
 *
 * Pour lire : `adb logcat -s Phototheque`.
 *
 * La mise en forme ([decrire]) est séparée de l'écriture ([info]) : la
 * première est pure et vérifiée sur la JVM, la seconde n'existe que sur un
 * appareil (`android.util.Log` n'est qu'une coquille vide dans les tests).
 */
object Journal {
    const val ETIQUETTE = "Phototheque"

    /** Résume une issue en une ligne. L'ordre des cas suit leur gravité. */
    fun decrire(issue: IssueSynchro): String {
        val bilan = issue.bilan
        return when {
            issue.revoque -> "appareil révoqué par le serveur"
            issue.erreur != null -> "en erreur : ${issue.erreur}"
            issue.serveurIntrouvable -> "serveur introuvable sur le réseau (pas une panne)"
            bilan != null -> {
                val etat = if (bilan.interrompu) "interrompue" else "terminée"
                // `null` et une carte vide ne disent pas la même chose (voir
                // IssueSynchro.dossiersVus) : on ne les confond pas ici non plus.
                val dossiers = issue.dossiersVus?.let { "${it.size} dossiers" }
                    ?: "dossiers non lus"
                // Issue #36 : le gel coûte une réempreinte à chaque passe ;
                // le journal doit le dire aussi, pas seulement l'accueil.
                val gel = if (bilan.gelesParLaDate.isEmpty()) ""
                    else ", horizon gelé par la date de début : " +
                        bilan.gelesParLaDate.sorted().joinToString(", ")
                "$etat : ${bilan.envoyes} envoyés, ${bilan.refuses} refusés, " +
                    "${bilan.echecs} en échec, $dossiers$gel"
            }
            else -> "sans issue publiée"
        }
    }

    /**
     * La file qui a lancé ce travail, lue sur ses étiquettes (posées par
     * `TravailSynchro.lancer` et `planifier`). Sans elle, le journal ne dirait
     * pas laquelle des deux files a tourné — exactement ce qui manquait pour
     * démêler le constat C1.
     */
    fun file(etiquettes: Set<String>): String = when {
        TravailSynchro.NOM_PERIODIQUE in etiquettes -> "auto"
        TravailSynchro.NOM in etiquettes -> "manuelle"
        else -> "file inconnue"
    }

    fun info(message: String) {
        Log.i(ETIQUETTE, message)
    }
}
