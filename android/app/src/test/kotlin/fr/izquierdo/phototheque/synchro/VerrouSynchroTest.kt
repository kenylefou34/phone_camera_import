package fr.izquierdo.phototheque.synchro

import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * VerrouSynchro est un singleton (`object` Kotlin), donc partagé par toute la
 * JVM de test : sans le libérer après chaque test, l'ordre d'exécution des
 * tests changerait le résultat.
 */
class VerrouSynchroTest {

    @After fun liberer_apres_chaque_test() {
        VerrouSynchro.liberer()
    }

    @Test fun un_verrou_libre_se_prend() {
        assertTrue(VerrouSynchro.tenter())
    }

    @Test fun un_second_tenter_echoue_tant_que_le_verrou_est_pris() {
        assertTrue(VerrouSynchro.tenter())
        assertFalse(VerrouSynchro.tenter())
    }

    @Test fun apres_liberer_un_nouveau_tenter_reussit() {
        VerrouSynchro.tenter()
        VerrouSynchro.liberer()
        assertTrue(VerrouSynchro.tenter())
    }
}
