package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReglagesTest {

    @Test fun cocher_auto_efface_la_date_de_fin() {
        // C'est la seule protection fiable contre la date de fin oubliée : un
        // compteur « 342 médias hors fenêtre » se remarque une semaine, pas
        // six mois.
        val avant = Reglages(debutJour = "2019-01-01", finJour = "2020-12-31")

        val apres = avant.enAuto()

        assertTrue(apres.auto)
        assertNull(apres.finJour)
        assertEquals("2019-01-01", apres.debutJour)   // la borne basse reste
    }

    @Test fun les_reglages_survivent_a_un_aller_retour_par_json() {
        val reglages = Reglages(
            dossiersSeuls = setOf("DCIM/Camera"),
            dossiersRecursifs = setOf("Pictures"),
            debutJour = "2026-09-15", finJour = null,
            debutApplique = "2026-09-15", auto = true)

        assertEquals(reglages, Reglages.depuisJson(reglages.versJson()))
    }

    @Test fun un_json_absent_donne_les_trois_dossiers_historiques() {
        // Une mise à jour de l'application ne doit RIEN changer à ce qui est
        // sauvegardé tant que l'utilisateur n'a rien choisi.
        assertEquals(Reglages.DEFAUT, Reglages.depuisJson(null))
        assertEquals(
            setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"),
            Reglages.DEFAUT.dossiersSeuls)
    }

    @Test fun un_json_illisible_ne_fait_pas_planter_et_retombe_sur_le_defaut() {
        // Préférences corrompues, rétrogradage de version : lever ici fermerait
        // l'application à CHAQUE lancement, définitivement.
        assertEquals(Reglages.DEFAUT, Reglages.depuisJson("{ceci n'est pas du json"))
    }
}
