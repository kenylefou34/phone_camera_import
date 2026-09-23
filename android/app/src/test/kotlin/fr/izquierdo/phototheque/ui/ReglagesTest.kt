package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReglagesTest {

    @Test
    fun `cocher auto efface la date de fin`() {
        // C'est la seule protection fiable contre la date de fin oubliee : un
        // compteur « 342 medias hors fenetre » se remarque une semaine, pas
        // six mois.
        val avant = Reglages(debutJour = "2019-01-01", finJour = "2020-12-31")

        val apres = avant.enAuto()

        assertTrue(apres.auto)
        assertNull(apres.finJour)
        assertEquals("2019-01-01", apres.debutJour)   // la borne basse reste
    }

    @Test
    fun `les reglages survivent a un aller-retour par json`() {
        val reglages = Reglages(
            dossiersSeuls = setOf("DCIM/Camera"),
            dossiersRecursifs = setOf("Pictures"),
            debutJour = "2026-09-15", finJour = null,
            debutApplique = "2026-09-15", auto = true)

        assertEquals(reglages, Reglages.depuisJson(reglages.versJson()))
    }

    @Test
    fun `un json absent donne les trois dossiers historiques`() {
        // Une mise a jour de l'application ne doit RIEN changer a ce qui est
        // sauvegarde tant que l'utilisateur n'a rien choisi.
        assertEquals(Reglages.DEFAUT, Reglages.depuisJson(null))
        assertEquals(
            setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"),
            Reglages.DEFAUT.dossiersSeuls)
    }

    @Test
    fun `un json illisible ne fait pas planter et retombe sur le defaut`() {
        // Preferences corrompues, retrogradage de version : lever ici fermerait
        // l'application a CHAQUE lancement, definitivement.
        assertEquals(Reglages.DEFAUT, Reglages.depuisJson("{ceci n'est pas du json"))
    }
}
