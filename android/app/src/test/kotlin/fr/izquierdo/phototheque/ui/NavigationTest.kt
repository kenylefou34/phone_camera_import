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

    @Test fun une_synchro_en_cours_ne_maintient_pas_un_appareil_revoque_sur_l_accueil() {
        // Cet état est ATTEIGNABLE, contrairement à ce qu'on croirait : une
        // révocation en pleine synchro fait appeler Coffre.oublier() par
        // TravailSynchro (TravailSynchro.kt:163), donc `appaire` retombe à
        // faux pendant que l'avancement n'est pas encore effacé. Si l'ordre
        // des deux gardes s'inversait, l'application afficherait l'accueil
        // d'un appareil qui n'a plus de jeton, au lieu de l'écran de scan.
        // C'est ce test, et lui seul, qui verrouille cet ordre.
        assertEquals(Ecran.APPAIRAGE,
            Navigation.ecranAffiche(Ecran.ACCUEIL, appaire = false, synchroEnCours = true))
    }

    @Test fun perdre_l_appairage_oublie_l_ecran_demande() {
        // Constat C3 de la recette du 24/09 : on désappaire depuis « Cet
        // appareil », la demande mémorisée reste APPAREIL, et le réappairage
        // suivant rouvre directement l'écran... qui propose de désappairer.
        // Un scan fait le téléphone tourné l'a fait appuyer dessus : un vrai
        // désappairage accidentel, constaté dans le journal du NUC.
        for (demande in Ecran.values()) {
            assertEquals(Ecran.ACCUEIL, Navigation.demandeApres(demande, appaire = false))
        }
    }

    @Test fun rester_appaire_garde_l_ecran_demande() {
        // Sans quoi une rotation ramènerait à l'accueil (issue #24).
        for (demande in Ecran.values()) {
            assertEquals(demande, Navigation.demandeApres(demande, appaire = true))
        }
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
