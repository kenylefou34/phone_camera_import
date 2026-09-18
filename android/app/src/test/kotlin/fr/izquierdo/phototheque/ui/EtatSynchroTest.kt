package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Le compteur part de la derniere synchro REUSSIE, jamais de la derniere
 * tentative : les pires pannes sont celles ou rien ne se passe, et ou il n'y a
 * donc aucun echec a signaler.
 */
class EtatSynchroTest {

    private val jour = 24 * 3600 * 1000L

    @Test fun jamais_synchronise_ne_donne_aucun_compteur() {
        assertNull(EtatSynchro.joursDepuis(maintenantMs = 10 * jour, derniereReussiteMs = null))
    }

    @Test fun compte_les_jours_entiers_ecoules() {
        assertEquals(3L, EtatSynchro.joursDepuis(10 * jour, 7 * jour))
        assertEquals(0L, EtatSynchro.joursDepuis(10 * jour, 10 * jour))
    }

    @Test fun le_seuil_d_alerte_est_a_sept_jours() {
        assertEquals(7L, EtatSynchro.SEUIL_ALERTE_JOURS)
    }

    @Test fun un_appareil_non_appaire_et_un_qr_invalide_sont_deux_etats_distincts() {
        // Sans cette distinction, l'ecran d'appairage ne saurait pas s'il doit
        // afficher un message d'erreur ou seulement l'invitation a scanner.
        val neuf = EtatSynchro()
        val refuse = EtatSynchro(qrInvalide = true)
        assertFalse(neuf.qrInvalide)
        assertTrue(refuse.qrInvalide)
        assertFalse(refuse.appaire)
    }
}
