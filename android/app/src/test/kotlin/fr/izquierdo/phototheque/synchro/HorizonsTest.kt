package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
        assertEquals(mapOf("DCIM/Camera" to 200.0), Horizons.calculer(envois).horizons)
    }

    @Test fun un_echec_au_milieu_arrete_l_horizon_avant_lui() {
        // Le fichier a 300 REUSSIT, mais celui a 200 a echoue : retenir 300
        // ferait sauter l'horizon par-dessus 200, plus jamais propose.
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.ECHEC),
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("DCIM/Camera" to 100.0), Horizons.calculer(envois).horizons)
    }

    @Test fun une_extension_refusee_ne_bloque_pas_l_horizon() {
        // 400 « extension non prise en charge » n'est PAS un echec : bloquer
        // dessus fermerait le dossier a jamais (contrat, section 6).
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.IGNORE),
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("DCIM/Camera" to 300.0), Horizons.calculer(envois).horizons)
    }

    @Test fun le_premier_fichier_echoue_le_dossier_est_absent_du_resultat() {
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.ECHEC),
            Envoi("DCIM/Camera", 200.0, Issue.CONFIRME),
        )
        assertFalse("DCIM/Camera" in Horizons.calculer(envois).horizons)
    }

    @Test fun un_dossier_en_echec_n_affecte_pas_les_autres() {
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.ECHEC),
            Envoi("Pictures/WhatsApp", 150.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("Pictures/WhatsApp" to 150.0), Horizons.calculer(envois).horizons)
    }

    @Test fun l_ordre_de_la_liste_n_influence_pas_le_resultat() {
        // La regle doit dependre des DATES, pas de l'ordre d'arrivee.
        val envois = listOf(
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.ECHEC),
        )
        assertEquals(mapOf("DCIM/Camera" to 100.0), Horizons.calculer(envois).horizons)
    }

    @Test fun aucun_envoi_aucun_horizon() {
        assertEquals(emptyMap<String, Double>(), Horizons.calculer(emptyList()).horizons)
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
        assertEquals(mapOf("DCIM/Camera" to 200.0), Horizons.calculer(envois).horizons)
    }

    @Test fun a_date_egale_l_echec_l_emporte_quel_que_soit_l_ordre() {
        val confirme = Envoi("DCIM/Camera", 200.0, Issue.CONFIRME)
        val echec = Envoi("DCIM/Camera", 200.0, Issue.ECHEC)
        // Meme ensemble d'evenements, deux ordres : meme resultat.
        assertEquals(
            Horizons.calculer(listOf(confirme, echec)),
            Horizons.calculer(listOf(echec, confirme)))
        // Et c'est la branche prudente qui est retenue : l'horizon n'avance pas.
        assertFalse("DCIM/Camera" in Horizons.calculer(listOf(confirme, echec)).horizons)
    }

    @Test fun un_dossier_deja_arrete_ne_bouge_plus_meme_si_le_paquet_reussit() {
        // Paquet 12 : DCIM/Camera a echoue. Paquet 13 : il reussit.
        // Sans memoire entre paquets, l'horizon sauterait PAR-DESSUS le
        // fichier en echec, qui ne serait PLUS JAMAIS propose par le serveur.
        val resultat = Horizons.calculer(
            listOf(Envoi("DCIM/Camera", 3000.0, Issue.CONFIRME)),
            dejaArretes = setOf("DCIM/Camera"),
        )
        assertFalse(resultat.horizons.containsKey("DCIM/Camera"))
    }

    @Test fun un_dossier_arrete_n_arrete_pas_les_autres() {
        val resultat = Horizons.calculer(
            listOf(
                Envoi("DCIM/Camera", 3000.0, Issue.CONFIRME),
                Envoi("Pictures/WhatsApp", 3000.0, Issue.CONFIRME),
            ),
            dejaArretes = setOf("DCIM/Camera"),
        )
        assertFalse(resultat.horizons.containsKey("DCIM/Camera"))
        assertEquals(3000.0, resultat.horizons["Pictures/WhatsApp"]!!, 0.0)
    }

    @Test fun les_dossiers_arretes_sont_rendus_pour_le_paquet_suivant() {
        val resultat = Horizons.calculer(
            listOf(
                Envoi("DCIM/Camera", 1000.0, Issue.CONFIRME),
                Envoi("DCIM/Camera", 2000.0, Issue.ECHEC),
            ),
        )
        assertEquals(setOf("DCIM/Camera"), resultat.arretes)
        assertEquals(1000.0, resultat.horizons["DCIM/Camera"]!!, 0.0)
    }

    @Test fun les_arretes_recus_sont_conserves_dans_le_resultat() {
        // Sans cela, l'appelant qui repasse `resultat.arretes` au paquet
        // suivant perdrait la memoire des paquets precedents des qu'un paquet
        // ne contient aucun media du dossier fautif.
        val resultat = Horizons.calculer(
            listOf(Envoi("Movies/WhatsApp", 5000.0, Issue.CONFIRME)),
            dejaArretes = setOf("DCIM/Camera"),
        )
        assertTrue(resultat.arretes.contains("DCIM/Camera"))
    }

    @Test fun un_refus_d_extension_n_arrete_toujours_pas_le_dossier() {
        // IGNORE n'est pas un echec : bloquer l'horizon dessus fermerait le
        // dossier a jamais, puisque le serveur refusera toujours ce fichier.
        val resultat = Horizons.calculer(
            listOf(
                Envoi("DCIM/Camera", 1000.0, Issue.IGNORE),
                Envoi("DCIM/Camera", 2000.0, Issue.CONFIRME),
            ),
        )
        assertEquals(2000.0, resultat.horizons["DCIM/Camera"]!!, 0.0)
        assertTrue(resultat.arretes.isEmpty())
    }

    @Test fun un_horizon_ne_recule_jamais() {
        // Le téléphone a tout jusqu'en septembre 2026. Une fenêtre 2019-2020 est
        // posée pour rattraper du vieux. Sans cette règle, le commit envoie
        // « fin 2020 » et le serveur ÉCRASE la mémoire de 2026 : la nuit suivante,
        // six ans de médias sont reproposés. Rien n'est perdu ni renvoyé deux
        // fois, mais le téléphone relit tout, à chaque fois.
        val nouveaux = mapOf("DCIM/Camera" to 1_609_459_200.0)   // 01/01/2021
        val connus = mapOf("DCIM/Camera" to 1_789_000_000.0)     // 2026

        assertEquals(mapOf("DCIM/Camera" to 1_789_000_000.0),
                     Horizons.monotone(nouveaux, connus))
    }

    @Test fun un_horizon_avance_normalement_quand_il_progresse() {
        val nouveaux = mapOf("DCIM/Camera" to 1_789_000_000.0)
        val connus = mapOf("DCIM/Camera" to 1_609_459_200.0)

        assertEquals(mapOf("DCIM/Camera" to 1_789_000_000.0),
                     Horizons.monotone(nouveaux, connus))
    }

    @Test fun un_dossier_sans_horizon_connu_garde_sa_valeur_neuve() {
        // Premier passage sur un dossier qu'on vient de cocher : il n'y a pas de
        // plancher à respecter, et en inventer un sauterait des médias.
        assertEquals(mapOf("Pictures/Messages" to 42.0),
                     Horizons.monotone(mapOf("Pictures/Messages" to 42.0), emptyMap()))
    }

    @Test fun un_dossier_connu_mais_absent_du_lot_n_est_pas_reenvoye() {
        // On ne transmet QUE ce que ce paquet a touché : renvoyer les autres
        // ferait écrire au serveur des horizons qu'aucun envoi ne justifie.
        assertEquals(emptyMap<String, Double>(),
                     Horizons.monotone(emptyMap(), mapOf("DCIM/Camera" to 1.0)))
    }
}
