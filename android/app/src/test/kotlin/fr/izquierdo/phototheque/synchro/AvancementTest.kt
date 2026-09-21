package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

class AvancementTest {

    @Test fun le_pourcentage_se_calcule_sur_les_octets_pas_sur_les_fichiers() {
        // 9 petites photos et 1 grosse video : compter en fichiers annoncerait
        // 90 % alors que l'essentiel du travail reste a faire.
        val a = Avancement(phase = Phase.ENVOI, fichiersFaits = 9, fichiersTotal = 10,
                           octetsFaits = 100, octetsTotal = 1000)
        assertEquals(10, a.pourcentage)
    }

    @Test fun un_total_nul_ne_divise_pas_par_zero() {
        // Une synchro sans rien a envoyer est le cas COURANT en regime
        // permanent : elle ne doit pas faire planter l'ecran.
        val a = Avancement(phase = Phase.ENVOI, fichiersFaits = 0, fichiersTotal = 0,
                           octetsFaits = 0, octetsTotal = 0)
        assertEquals(0, a.pourcentage)
    }

    @Test fun le_pourcentage_ne_depasse_jamais_cent() {
        val a = Avancement(phase = Phase.ENVOI, fichiersFaits = 1, fichiersTotal = 1,
                           octetsFaits = 2000, octetsTotal = 1000)
        assertEquals(100, a.pourcentage)
    }

    @Test fun un_avancement_neuf_est_en_phase_d_analyse() {
        assertEquals(Phase.ANALYSE, Avancement().phase)
    }

    @Test fun les_champs_d_affichage_sont_absents_par_defaut() {
        val a = Avancement()
        assertEquals(null, a.mediaEnCours)
        assertEquals(null, a.destinationPrevue)
        assertEquals(null, a.octetsParSeconde)
        assertEquals(null, a.secondesRestantes)
    }
}
