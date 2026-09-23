package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.ui.Reglages
import org.junit.Assert.assertEquals
import org.junit.Test

class TravailSynchroReglagesTest {

    @Test fun les_dossiers_synchronises_viennent_des_reglages_et_non_de_la_constante() {
        val reglages = Reglages(dossiersSeuls = setOf("Pictures/Messages"))

        val choisis = TravailSynchro.dossiersASauvegarder(
            reglages, tous = setOf("Pictures/Messages", "DCIM/Camera"))

        assertEquals(setOf("Pictures/Messages"), choisis)
    }

    @Test fun des_reglages_vierges_sauvegardent_les_trois_dossiers_historiques() {
        // Une mise à jour ne doit RIEN changer tant que l'utilisateur n'a pas
        // ouvert l'écran.
        val choisis = TravailSynchro.dossiersASauvegarder(
            Reglages.DEFAUT,
            tous = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp", "Download"))

        assertEquals(setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"), choisis)
    }
}
