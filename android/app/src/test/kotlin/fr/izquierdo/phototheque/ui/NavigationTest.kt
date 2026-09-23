package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NavigationTest {

    @Test fun sans_appairage_aucun_autre_ecran_n_est_atteignable() {
        // Le lot 1 le garantissait par un `when` ; il faut que ça reste vrai
        // maintenant que sept destinations existent.
        for (demande in Ecran.values()) {
            assertEquals(Ecran.APPAIRAGE,
                Navigation.ecranAffiche(demande, appaire = false, synchroEnCours = false))
        }
    }

    @Test fun une_synchro_en_cours_prend_le_pas_sur_l_ecran_demande() {
        assertEquals(Ecran.ACCUEIL,
            Navigation.ecranAffiche(Ecran.DOSSIERS, appaire = true, synchroEnCours = true))
    }

    @Test fun l_ecran_demande_est_affiche_quand_rien_ne_s_y_oppose() {
        assertEquals(Ecran.DOSSIERS,
            Navigation.ecranAffiche(Ecran.DOSSIERS, appaire = true, synchroEnCours = false))
    }

    @Test fun les_trois_ecrans_de_reglages_reviennent_aux_reglages() {
        assertEquals(Ecran.REGLAGES, Navigation.retour(Ecran.DOSSIERS))
        assertEquals(Ecran.REGLAGES, Navigation.retour(Ecran.SAUVEGARDE))
        assertEquals(Ecran.REGLAGES, Navigation.retour(Ecran.APPAREIL))
    }

    @Test fun l_accueil_n_a_pas_de_retour_et_ferme_l_application() {
        // null = on laisse le système fermer l'application. Renvoyer ACCUEIL
        // ici rendrait le bouton retour inopérant, ce qui se signale en
        // magasin d'applications comme un défaut.
        assertNull(Navigation.retour(Ecran.ACCUEIL))
        assertNull(Navigation.retour(Ecran.APPAIRAGE))
    }
}
