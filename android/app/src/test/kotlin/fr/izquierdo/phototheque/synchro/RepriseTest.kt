package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RepriseTest {

    private fun bilan(echecs: Int = 0, revoque: Boolean = false,
                      interrompu: Boolean = false) =
        Bilan(envoyes = 0, refuses = 0, echecs = echecs, revoque = revoque,
              bilanServeur = emptyMap(), interrompu = interrompu)

    @Test fun une_synchro_reussie_ne_se_relance_pas() {
        assertFalse(Reprise.fautIlRelancer(bilan()))
    }

    @Test fun un_echec_reseau_se_relance() {
        assertTrue(Reprise.fautIlRelancer(bilan(echecs = 3)))
    }

    @Test fun un_arret_demande_ne_se_relance_JAMAIS() {
        // Un arret que l'utilisateur a demande ne doit pas se defaire tout
        // seul : ce serait le contraire de ce qu'il vient de demander.
        assertFalse(Reprise.fautIlRelancer(bilan(echecs = 5, interrompu = true)))
    }

    @Test fun une_revocation_ne_se_relance_pas() {
        // Seul un nouveau QR debloque : relancer tournerait en boucle.
        assertFalse(Reprise.fautIlRelancer(bilan(echecs = 2, revoque = true)))
    }

    @Test fun un_lancement_refuse_par_le_verrou_se_relance_toujours() {
        // Constat C1 de la recette du 24/09 : un lancement refusé par
        // VerrouSynchro sortait en « réussite » muette. La passe automatique
        // attendait alors six heures, et « Sauvegarder maintenant » ne
        // faisait rien. Sans plafond, à la différence d'une panne : le verrou
        // finit toujours par être rendu, et plafonner retomberait dans
        // l'abandon muet dès que la synchro qui le tient dure plus de
        // quelques minutes (gros fichier, issue #33). D'où l'absence de tout
        // paramètre : aucun compte de tentatives ne peut y changer quoi que
        // ce soit (relecture finale, M14).
        assertTrue(Reprise.apresRefusDuVerrou())
    }
}
