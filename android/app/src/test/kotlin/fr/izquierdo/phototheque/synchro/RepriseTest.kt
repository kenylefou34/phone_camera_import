package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RepriseTest {

    private fun bilan(echecs: Int = 0, revoque: Boolean = false,
                      interrompu: Boolean = false) =
        Bilan(envoyes = 0, refuses = 0, echecs = echecs, revoque = revoque,
              bilanServeur = emptyMap(), interrompu = interrompu)

    @Test fun une_synchro_reussie_ne_se_relance_pas() {
        assertFalse(Reprise.fautIlRelancer(bilan()))
    }

    @Test fun un_echec_reseau_se_relance() {
        assertTrue(Reprise.fautIlRelancer(bilan(echecs = 3)))
    }

    @Test fun un_arret_demande_ne_se_relance_JAMAIS() {
        // Un arret que l'utilisateur a demande ne doit pas se defaire tout
        // seul : ce serait le contraire de ce qu'il vient de demander.
        assertFalse(Reprise.fautIlRelancer(bilan(echecs = 5, interrompu = true)))
    }

    @Test fun une_revocation_ne_se_relance_pas() {
        // Seul un nouveau QR debloque : relancer tournerait en boucle.
        assertFalse(Reprise.fautIlRelancer(bilan(echecs = 2, revoque = true)))
    }
}
