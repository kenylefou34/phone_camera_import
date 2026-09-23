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

    // --- Ronde de correction 1/5 : avant/après séparés, fenêtre inversée ---

    @Test fun avant_la_fenetre_compte_les_medias_plus_anciens_que_le_debut() {
        // Comptes volontairement ASYMÉTRIQUES (2 vieux, 1 récent) : si
        // avantLaFenetre et apresLaFenetre étaient un jour intervertis par
        // erreur, ce test doit le voir plutôt que de tomber par coïncidence
        // sur le même total.
        val medias = listOf(
            media(instantLocal("2018-01-01T12:00", "Europe/Paris")),
            media(instantLocal("2019-06-01T12:00", "Europe/Paris")),
            media(instantLocal("2026-09-20T12:00", "Europe/Paris")))
        assertEquals(2, Fenetre.avantLaFenetre(medias, "2020-01-01"))
    }

    @Test fun avant_la_fenetre_sans_debut_ne_compte_rien() {
        val medias = listOf(media(instantLocal("2019-01-01T12:00", "Europe/Paris")))
        assertEquals(0, Fenetre.avantLaFenetre(medias, null))
    }

    @Test fun apres_la_fenetre_compte_les_medias_plus_recents_que_la_fin() {
        // Comptes asymétriques (1 vieux, 2 récents), même raison que ci-dessus.
        val medias = listOf(
            media(instantLocal("2019-01-01T12:00", "Europe/Paris")),
            media(instantLocal("2026-09-20T12:00", "Europe/Paris")),
            media(instantLocal("2026-09-21T12:00", "Europe/Paris")))
        assertEquals(2, Fenetre.apresLaFenetre(medias, "2026-01-01"))
    }

    @Test fun apres_la_fenetre_sans_fin_ne_compte_rien() {
        val medias = listOf(media(instantLocal("2026-09-20T12:00", "Europe/Paris")))
        assertEquals(0, Fenetre.apresLaFenetre(medias, null))
    }

    @Test fun une_fenetre_inversee_est_detectee() {
        assertTrue(Fenetre.fenetreInversee(debut = "2026-09-01", fin = "2026-01-01"))
    }

    @Test fun une_fenetre_normale_n_est_pas_inversee() {
        assertFalse(Fenetre.fenetreInversee(debut = "2026-01-01", fin = "2026-09-01"))
    }

    @Test fun une_fenetre_d_un_seul_jour_n_est_pas_inversee() {
        // Bord important : debut == fin est une fenêtre valide (un seul
        // jour), pas une inversion. Une comparaison au sens large (>=) au
        // lieu de isAfter la marquerait à tort comme inversée.
        assertFalse(Fenetre.fenetreInversee(debut = "2026-09-01", fin = "2026-09-01"))
    }

    @Test fun une_seule_borne_posee_n_est_jamais_inversee() {
        assertFalse(Fenetre.fenetreInversee(debut = "2026-09-01", fin = null))
        assertFalse(Fenetre.fenetreInversee(debut = null, fin = "2026-09-01"))
    }
}
