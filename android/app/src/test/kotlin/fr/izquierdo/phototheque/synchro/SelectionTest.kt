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

    @Test fun un_ordre_de_reprise_passe_sous_l_horizon_connu() {
        // Abaisser la date de début doit REPROPOSER les vieux médias. Sans ce
        // plancher, `horizons[dossier] ?: depuis` fait toujours gagner
        // l'horizon et la date de début ne peut rien reprendre du tout.
        val vieux = Media(1, "DCIM/Camera", "a.jpg", 10, instant = 100.0)
        val recent = Media(2, "DCIM/Camera", "b.jpg", 10, instant = 900.0)

        val candidats = Selection.candidats(
            medias = listOf(vieux, recent),
            dossiersChoisis = setOf("DCIM/Camera"),
            horizons = mapOf("DCIM/Camera" to 500.0),
            depuisSecondes = null,
            plancherReprise = 50.0)

        assertEquals(listOf(vieux, recent), candidats)
    }

    @Test fun sans_ordre_de_reprise_l_horizon_commande_toujours() {
        // Régime par défaut du nouveau paramètre : `plancherReprise` à
        // `null` ne doit RIEN changer au comportement existant, c'est
        // l'horizon (ou `depuisSecondes`) qui commande seul.
        val vieux = Media(1, "DCIM/Camera", "a.jpg", 10, instant = 100.0)
        val recent = Media(2, "DCIM/Camera", "b.jpg", 10, instant = 900.0)

        val candidats = Selection.candidats(
            medias = listOf(vieux, recent),
            dossiersChoisis = setOf("DCIM/Camera"),
            horizons = mapOf("DCIM/Camera" to 500.0),
            depuisSecondes = null,
            plancherReprise = null)

        assertEquals(listOf(recent), candidats)
    }

    @Test fun un_ordre_de_reprise_plus_haut_que_l_horizon_ne_saute_aucun_media() {
        // Reprendre « depuis 2020 » sur un dossier dont l'horizon est à 2019
        // ne doit pas fermer la fenêtre 2019-2020 : la reprise ABAISSE le
        // plancher, elle ne le remonte jamais.
        val avantHorizon = Media(1, "DCIM/Camera", "z.jpg", 10, instant = 100.0)
        val media = Media(2, "DCIM/Camera", "a.jpg", 10, instant = 300.0)

        val candidats = Selection.candidats(
            medias = listOf(avantHorizon, media),
            dossiersChoisis = setOf("DCIM/Camera"),
            horizons = mapOf("DCIM/Camera" to 200.0),
            depuisSecondes = null,
            plancherReprise = 500.0)

        // La fenêtre 100-200 reste fermée : la reprise, plus haute que
        // l'horizon, ne l'a PAS rouverte.
        assertEquals(listOf(media), candidats)
    }

    @Test fun un_ordre_de_reprise_n_impose_aucun_plancher_la_ou_il_n_y_en_avait_pas() {
        // La reprise ABAISSE un plancher existant ; elle n'en crée jamais un
        // tout seul. Sans horizon et sans `depuisSecondes`, un dossier n'a
        // AUCUNE limite -- ce rôle de plancher permanent revient à
        // `depuisSecondes` (voir Orchestrateur.synchroniser, qui y fait
        // désormais porter la date de début), pas à la reprise.
        val vieux = Media(1, "DCIM/Camera", "a.jpg", 10, instant = 1.0)

        val candidats = Selection.candidats(
            medias = listOf(vieux),
            dossiersChoisis = setOf("DCIM/Camera"),
            horizons = emptyMap(),
            depuisSecondes = null,
            plancherReprise = 500.0)

        assertEquals(listOf(vieux), candidats)
    }
}
