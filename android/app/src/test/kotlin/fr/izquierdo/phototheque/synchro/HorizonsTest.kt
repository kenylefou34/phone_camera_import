package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/**
 * La règle de l'horizon, telle que la fixe docs/CONTRAT-APP.md §5 : c'est
 * l'APPLICATION qui décide, le serveur enregistre sans vérifier. Un horizon
 * avancé au-delà d'un fichier jamais reçu perd ce média définitivement et sans
 * le moindre signal.
 */
class HorizonsTest {

    @Test fun tout_reussit_l_horizon_vaut_le_dernier_fichier() {
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("DCIM/Camera" to 200.0), Horizons.calculer(envois))
    }

    @Test fun un_echec_au_milieu_arrete_l_horizon_avant_lui() {
        // Le fichier a 300 REUSSIT, mais celui a 200 a echoue : retenir 300
        // ferait sauter l'horizon par-dessus 200, plus jamais propose.
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.ECHEC),
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("DCIM/Camera" to 100.0), Horizons.calculer(envois))
    }

    @Test fun une_extension_refusee_ne_bloque_pas_l_horizon() {
        // 400 « extension non prise en charge » n'est PAS un echec : bloquer
        // dessus fermerait le dossier a jamais (contrat, section 6).
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.IGNORE),
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("DCIM/Camera" to 300.0), Horizons.calculer(envois))
    }

    @Test fun le_premier_fichier_echoue_le_dossier_est_absent_du_resultat() {
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.ECHEC),
            Envoi("DCIM/Camera", 200.0, Issue.CONFIRME),
        )
        assertFalse("DCIM/Camera" in Horizons.calculer(envois))
    }

    @Test fun un_dossier_en_echec_n_affecte_pas_les_autres() {
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.ECHEC),
            Envoi("Pictures/WhatsApp", 150.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("Pictures/WhatsApp" to 150.0), Horizons.calculer(envois))
    }

    @Test fun l_ordre_de_la_liste_n_influence_pas_le_resultat() {
        // La regle doit dependre des DATES, pas de l'ordre d'arrivee.
        val envois = listOf(
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.ECHEC),
        )
        assertEquals(mapOf("DCIM/Camera" to 100.0), Horizons.calculer(envois))
    }

    @Test fun aucun_envoi_aucun_horizon() {
        assertEquals(emptyMap<String, Double>(), Horizons.calculer(emptyList()))
    }

    @Test fun une_extension_refusee_en_DERNIER_fait_quand_meme_avancer_l_horizon() {
        // Le cas que le test precedent ne couvre pas : sans CONFIRME apres lui,
        // IGNORE est le seul evenement capable de faire avancer l'horizon. S'il
        // etait simplement saute, l'horizon resterait a 100.0, le fichier refuse
        // serait repropose a chaque synchro puis re-refuse, et tous les medias
        // suivants du dossier seraient sacrifies — le blocage permanent que le
        // contrat interdit (docs/CONTRAT-APP.md, section 6).
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.IGNORE),
        )
        assertEquals(mapOf("DCIM/Camera" to 200.0), Horizons.calculer(envois))
    }

    @Test fun a_date_egale_l_echec_l_emporte_quel_que_soit_l_ordre() {
        val confirme = Envoi("DCIM/Camera", 200.0, Issue.CONFIRME)
        val echec = Envoi("DCIM/Camera", 200.0, Issue.ECHEC)
        // Meme ensemble d'evenements, deux ordres : meme resultat.
        assertEquals(
            Horizons.calculer(listOf(confirme, echec)),
            Horizons.calculer(listOf(echec, confirme)))
        // Et c'est la branche prudente qui est retenue : l'horizon n'avance pas.
        assertFalse("DCIM/Camera" in Horizons.calculer(listOf(confirme, echec)))
    }
}
