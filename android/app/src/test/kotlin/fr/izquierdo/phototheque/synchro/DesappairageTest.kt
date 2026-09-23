package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DesappairageTest {

    @Test fun l_effacement_local_a_lieu_meme_quand_le_serveur_est_injoignable() {
        // C'est le cas NORMAL d'usage de cette fonction : on désappaire pour
        // se dépanner, et à ce moment-là le serveur est injoignable par
        // définition — certificat changé, machine réinstallée, autre serveur.
        // Faire dépendre le dépannage du serveur qu'on ne joint plus serait
        // exactement l'impasse qu'on corrige.
        var efface = false

        val resultat = Desappairage.executer(
            prevenirServeur = { throw java.io.IOException("injoignable") },
            effacerLocal = { efface = true })

        assertTrue(efface)
        assertFalse(resultat.serveurPrevenu)
    }

    @Test fun un_serveur_qui_refuse_n_empeche_pas_l_effacement() {
        var efface = false

        val resultat = Desappairage.executer(
            prevenirServeur = { false },
            effacerLocal = { efface = true })

        assertTrue(efface)
        assertFalse(resultat.serveurPrevenu)
    }

    @Test fun un_serveur_joignable_est_prevenu_et_l_effacement_a_lieu() {
        var efface = false

        val resultat = Desappairage.executer(
            prevenirServeur = { true },
            effacerLocal = { efface = true })

        assertTrue(efface)
        assertTrue(resultat.serveurPrevenu)
    }
}
