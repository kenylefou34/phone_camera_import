package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import java.time.LocalDateTime
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FenetreTest {

    private fun media(instant: Double) = Media(1, "DCIM/Camera", "a.jpg", 10, instant)

    /** Un instant réel, construit hors de Fenetre : c'est ce qui empêche ces
     *  tests d'être auto-cohérents et donc vides de sens. */
    private fun instantLocal(quand: String, fuseau: String): Double =
        LocalDateTime.parse(quand).atZone(ZoneId.of(fuseau)).toEpochSecond().toDouble()

    @Test fun sans_bornes_tout_est_dans_la_fenetre() {
        assertTrue(Fenetre.dansLaFenetre(media(0.0), null, null))
        assertTrue(Fenetre.dansLaFenetre(media(9e9), null, null))
    }

    @Test fun la_borne_de_fin_couvre_la_soiree_du_dernier_jour_partout() {
        // LE test de cette tâche. Une photo prise le 15 à 23 h doit rester
        // DANS une fenêtre qui finit le 15 — à Paris comme à Tokyo comme à
        // Los Angeles. Une borne calée sur minuit UTC, ou pire sur le début
        // de jour + 24 h, couperait l'après-midi et la soirée du dernier
        // jour sans un mot.
        for (fuseau in listOf("Europe/Paris", "Asia/Tokyo", "America/Los_Angeles")) {
            val tard = instantLocal("2026-09-15T23:00", fuseau)
            assertTrue(fuseau, Fenetre.dansLaFenetre(media(tard), null, "2026-09-15"))
        }
    }

    @Test fun la_borne_de_debut_couvre_le_petit_matin_du_premier_jour_partout() {
        for (fuseau in listOf("Europe/Paris", "Asia/Tokyo", "America/Los_Angeles")) {
            val tot = instantLocal("2026-09-15T00:30", fuseau)
            assertTrue(fuseau, Fenetre.dansLaFenetre(media(tot), "2026-09-15", null))
        }
    }

    @Test fun la_borne_de_fin_ecarte_bien_les_jours_suivants() {
        // La contrepartie : trop large ne veut pas dire sans borne.
        val bienApres = instantLocal("2026-09-20T12:00", "Europe/Paris")
        assertFalse(Fenetre.dansLaFenetre(media(bienApres), null, "2026-09-15"))
    }

    @Test fun une_fenetre_inversee_ne_retient_rien_et_ne_leve_pas() {
        // Début après fin : l'utilisateur s'est trompé. Zéro média, et
        // l'écran doit le DIRE - pas un comportement indéfini.
        val m = media(instantLocal("2026-06-01T12:00", "Europe/Paris"))
        assertFalse(Fenetre.dansLaFenetre(m, debut = "2026-09-01", fin = "2026-01-01"))
    }

    @Test fun hors_fenetre_compte_ce_que_la_fenetre_laisse_dehors() {
        val medias = listOf(
            media(instantLocal("2019-01-01T12:00", "Europe/Paris")),
            media(instantLocal("2026-09-20T12:00", "Europe/Paris")),
            media(instantLocal("2026-09-21T12:00", "Europe/Paris")))

        assertEquals(2, Fenetre.horsFenetre(medias, debut = null, fin = "2026-01-01"))
    }
}
