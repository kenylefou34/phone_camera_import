package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Constat C2 de la recette du 24/09 : l'application n'écrivait RIEN dans le
 * journal Android. Une passe automatique ne laissait aucune trace de son
 * issue ; il a fallu reconstituer ce qui s'était passé à partir de la base
 * interne de WorkManager. Ces lignes sont ce qu'on lira dans `adb logcat`.
 */
class JournalTest {

    private fun bilan(envoyes: Int = 0, refuses: Int = 0, echecs: Int = 0,
                      interrompu: Boolean = false) =
        Bilan(envoyes, refuses, echecs, revoque = false,
              bilanServeur = emptyMap(), interrompu = interrompu)

    @Test fun un_bilan_complet_donne_ses_trois_comptes() {
        assertEquals("terminée : 3 envoyés, 12 refusés, 0 en échec, 4 dossiers",
            Journal.decrire(IssueSynchro(bilan = bilan(3, 12, 0),
                dossiersVus = mapOf("a" to 1, "b" to 2, "c" to 3, "d" to 4))))
    }

    @Test fun un_gel_par_la_date_est_mentionne() {
        assertEquals("terminée : 0 envoyés, 5 refusés, 0 en échec, 1 dossiers, " +
                     "horizon gelé par la date de début : DCIM/Camera",
            Journal.decrire(IssueSynchro(
                bilan = bilan(refuses = 5).copy(gelesParLaDate = setOf("DCIM/Camera")),
                dossiersVus = mapOf("DCIM/Camera" to 5))))
    }

    @Test fun un_bilan_interrompu_le_dit() {
        assertEquals("interrompue : 1 envoyés, 0 refusés, 0 en échec, 1 dossiers",
            Journal.decrire(IssueSynchro(bilan = bilan(1, interrompu = true),
                dossiersVus = mapOf("a" to 1))))
    }

    @Test fun aucun_dossier_parcouru_est_distingue_d_un_dossier_vide() {
        // La carte VIDE est une vraie réponse de MediaStore (le cas le plus
        // grave) ; `null` veut dire qu'aucune lecture n'a eu lieu.
        assertEquals("terminée : 0 envoyés, 0 refusés, 0 en échec, 0 dossiers",
            Journal.decrire(IssueSynchro(bilan = bilan(), dossiersVus = emptyMap())))
        assertEquals("terminée : 0 envoyés, 0 refusés, 0 en échec, dossiers non lus",
            Journal.decrire(IssueSynchro(bilan = bilan(), dossiersVus = null)))
    }

    @Test fun le_serveur_introuvable_n_est_pas_une_panne() {
        assertEquals("serveur introuvable sur le réseau (pas une panne)",
            Journal.decrire(IssueSynchro(serveurIntrouvable = true)))
    }

    @Test fun la_revocation_prime_sur_le_bilan() {
        assertEquals("appareil révoqué par le serveur",
            Journal.decrire(IssueSynchro(bilan = bilan(2), revoque = true)))
    }

    @Test fun une_erreur_donne_son_message() {
        assertEquals("en erreur : délai dépassé",
            Journal.decrire(IssueSynchro(erreur = "délai dépassé")))
    }

    @Test fun la_file_se_lit_sur_les_etiquettes_du_travail() {
        // WorkManager ajoute toujours le nom de la classe aux étiquettes :
        // il ne doit pas être pris pour une file.
        val classe = "fr.izquierdo.phototheque.synchro.TravailSynchro"
        assertEquals("auto", Journal.file(setOf(classe, "synchro-auto")))
        assertEquals("manuelle", Journal.file(setOf(classe, "synchro")))
        // Un travail programmé avant l'ajout des étiquettes : on ne devine pas.
        assertEquals("file inconnue", Journal.file(setOf(classe)))
    }

    @Test fun une_issue_vide_ne_prétend_rien() {
        assertEquals("sans issue publiée", Journal.decrire(IssueSynchro()))
    }
}
