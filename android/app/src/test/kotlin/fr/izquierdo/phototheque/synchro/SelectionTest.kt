package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import org.junit.Assert.assertEquals
import org.junit.Test

class SelectionTest {

    private fun media(dossier: String, instant: Double, nom: String = "a.jpg") =
        Media(id = instant.toLong(), dossier = dossier, nom = nom,
              taille = 100L, instant = instant)

    @Test fun seuls_les_dossiers_coches_sont_retenus() {
        val medias = listOf(media("DCIM/Camera", 200.0), media("Pictures/Memes", 200.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"), emptyMap(), 0.0)
        assertEquals(listOf("DCIM/Camera"), r.map { it.dossier })
    }

    @Test fun ce_qui_precede_l_horizon_est_ecarte() {
        val medias = listOf(media("DCIM/Camera", 100.0), media("DCIM/Camera", 300.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"),
                                    mapOf("DCIM/Camera" to 200.0), 0.0)
        assertEquals(listOf(300.0), r.map { it.instant })
    }

    @Test fun le_fichier_exactement_a_l_horizon_est_REPROPOSE() {
        // Comparaison >= et non > : DATE_MODIFIED est en secondes, deux photos
        // d'une rafale peuvent porter la meme valeur. Avec >, la seconde serait
        // perdue a jamais. Reproposer est benin (l'anti-doublon ecarte sans
        // transferer), sauter est definitif. Voir la spec, section 5.
        val medias = listOf(media("DCIM/Camera", 200.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"),
                                    mapOf("DCIM/Camera" to 200.0), 0.0)
        assertEquals(1, r.size)
    }

    @Test fun un_dossier_sans_horizon_retombe_sur_depuis() {
        val medias = listOf(media("DCIM/Camera", 100.0), media("DCIM/Camera", 300.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"), emptyMap(), 200.0)
        assertEquals(listOf(300.0), r.map { it.instant })
    }

    @Test fun depuis_absent_signifie_aucune_limite() {
        // /sync/horizon peut renvoyer depuis = null pour un appareil repris.
        val medias = listOf(media("DCIM/Camera", 1.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"), emptyMap(), null)
        assertEquals(1, r.size)
    }

    @Test fun les_candidats_sortent_tries_par_date_croissante() {
        // C'est ce qui donne un sens a « le dernier confirme » (Horizons).
        val medias = listOf(media("DCIM/Camera", 300.0), media("DCIM/Camera", 100.0),
                            media("DCIM/Camera", 200.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"), emptyMap(), null)
        assertEquals(listOf(100.0, 200.0, 300.0), r.map { it.instant })
    }
}
