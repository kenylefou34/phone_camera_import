package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Ce qui est verifiable ici, et ce qui ne l'est pas.
 *
 * L'aller-retour reel dans les SharedPreferences demande un vrai appareil ou
 * Robolectric : dans un test JVM ordinaire, android.jar n'est qu'un squelette
 * et getSharedPreferences leve "not mocked". Ce que l'on peut verrouiller, et
 * qui compte, c'est la traduction de la valeur brute : getLong rend 0 quand la
 * cle n'existe pas, et confondre ce 0 avec une date ferait afficher un nombre
 * de jours calcule depuis 1970 au lieu du "Jamais sauvegarde" attendu sur une
 * installation neuve.
 */
class MemoireTest {

    @Test fun une_installation_neuve_n_a_jamais_ete_sauvegardee() {
        assertNull(Memoire.instantOuJamais(0L))
    }

    @Test fun un_instant_enregistre_est_rendu_tel_quel() {
        assertEquals(1789000000000L, Memoire.instantOuJamais(1789000000000L))
    }

    @Test fun un_instant_aberrant_vaut_jamais_plutot_qu_une_date_negative() {
        // Une valeur negative ne peut venir que d'une preference abimee. La
        // rendre donnerait un compteur de jours negatif, c'est-a-dire une
        // sauvegarde dans le futur : mieux vaut avouer qu'on ne sait pas.
        assertNull(Memoire.instantOuJamais(-1L))
    }
}
