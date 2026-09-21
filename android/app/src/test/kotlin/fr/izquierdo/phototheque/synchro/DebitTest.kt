package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DebitTest {

    @Test fun sans_mesure_le_debit_est_inconnu() {
        // Inconnu, PAS zero : afficher « 0 Mo/s » au demarrage ferait croire
        // a un blocage.
        assertNull(Debit().octetsParSeconde(1000L))
    }

    @Test fun une_seule_mesure_ne_suffit_pas() {
        // Une mesure ne donne aucune duree : un debit calcule dessus serait
        // une division par zero, ou un nombre invente.
        val d = Debit()
        d.ajouter(1000, 0L)
        assertNull(d.octetsParSeconde(0L))
    }

    @Test fun deux_mesures_donnent_un_debit() {
        val d = Debit()
        d.ajouter(0, 0L)
        d.ajouter(2000, 2000L)          // 2000 octets en 2 s
        assertEquals(1000.0, d.octetsParSeconde(2000L)!!, 1.0)
    }

    @Test fun les_mesures_trop_vieilles_sortent_de_la_fenetre() {
        // Moyenne GLISSANTE : une video enorme envoyee il y a cinq minutes ne
        // doit plus peser sur l'estimation d'un lot de petites photos.
        val d = Debit(fenetreMs = 10_000L)
        d.ajouter(0, 0L)
        d.ajouter(1_000_000, 1_000L)    // tres rapide, puis oublie
        d.ajouter(1_000_100, 20_000L)   // tres lent, dans la fenetre
        val vu = d.octetsParSeconde(20_000L)!!
        assertTrue("debit=$vu devrait etre faible", vu < 1000.0)
    }

    @Test fun le_temps_restant_est_inconnu_sans_debit() {
        assertNull(Debit().secondesRestantes(5000, 1000L))
    }

    @Test fun le_temps_restant_se_deduit_du_debit() {
        val d = Debit()
        d.ajouter(0, 0L)
        d.ajouter(1000, 1000L)          // 1000 octets/s
        assertEquals(5L, d.secondesRestantes(5000, 1000L))
    }

    @Test fun un_reste_nul_donne_zero_seconde() {
        val d = Debit()
        d.ajouter(0, 0L)
        d.ajouter(1000, 1000L)
        assertEquals(0L, d.secondesRestantes(0, 1000L))
    }

    @Test fun un_debit_nul_ne_divise_pas_par_zero() {
        // Deux mesures au meme instant, ou aucun octet transfere : le calcul
        // rendrait Infinity, et l'ecran afficherait « ~ Infinity min ».
        val d = Debit()
        d.ajouter(500, 0L)
        d.ajouter(500, 5000L)           // zero octet en 5 s
        assertNull(d.secondesRestantes(1000, 5000L))
    }
}
