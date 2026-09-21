package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PaquetsTest {

    private fun media(id: Long, taille: Long, instant: Double) =
        Media(id = id, dossier = "DCIM/Camera", nom = "m$id.jpg",
              taille = taille, instant = instant)

    @Test fun une_liste_vide_ne_donne_aucun_paquet() {
        assertTrue(Paquets.decouper(emptyList()).isEmpty())
    }

    @Test fun les_medias_tiennent_dans_un_seul_paquet_sous_la_limite() {
        val lot = listOf(media(1, 100, 1.0), media(2, 100, 2.0))
        assertEquals(1, Paquets.decouper(lot, tailleMax = 1000).size)
    }

    @Test fun on_change_de_paquet_quand_la_limite_serait_depassee() {
        val lot = listOf(media(1, 600, 1.0), media(2, 600, 2.0))
        val paquets = Paquets.decouper(lot, tailleMax = 1000)
        assertEquals(2, paquets.size)
        assertEquals(1L, paquets[0].single().id)
        assertEquals(2L, paquets[1].single().id)
    }

    @Test fun un_media_plus_gros_que_la_limite_fait_son_paquet_a_lui_seul() {
        // Une video de 3 Go depasse n'importe quelle taille de paquet
        // raisonnable. La refuser, ou la couper, la perdrait.
        val lot = listOf(media(1, 5000, 1.0))
        val paquets = Paquets.decouper(lot, tailleMax = 1000)
        assertEquals(1, paquets.size)
        assertEquals(1L, paquets.single().single().id)
    }

    @Test fun un_media_enorme_ne_se_melange_pas_aux_suivants() {
        val lot = listOf(media(1, 5000, 1.0), media(2, 10, 2.0))
        val paquets = Paquets.decouper(lot, tailleMax = 1000)
        assertEquals(2, paquets.size)
        assertEquals(1L, paquets[0].single().id)
    }

    @Test fun aucun_media_n_est_perdu_ni_duplique() {
        val lot = (1L..50L).map { media(it, 300, it.toDouble()) }
        val plat = Paquets.decouper(lot, tailleMax = 1000).flatten()
        assertEquals(lot.map { it.id }, plat.map { it.id })
    }

    @Test fun l_ordre_par_date_croissante_est_conserve() {
        // L'ordre chronologique est ce qui rend la regle de l'horizon juste :
        // le melanger ferait avancer un horizon par-dessus un fichier plus
        // ancien pas encore envoye.
        val lot = listOf(media(1, 10, 100.0), media(2, 10, 200.0), media(3, 10, 300.0))
        val plat = Paquets.decouper(lot, tailleMax = 25).flatten()
        assertEquals(listOf(100.0, 200.0, 300.0), plat.map { it.instant })
    }

    @Test fun la_taille_par_defaut_est_de_500_Mo() {
        assertEquals(500L * 1024 * 1024, Paquets.TAILLE_MAX_OCTETS)
    }
}
