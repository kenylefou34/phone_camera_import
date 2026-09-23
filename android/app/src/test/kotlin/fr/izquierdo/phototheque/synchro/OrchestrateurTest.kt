package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import fr.izquierdo.phototheque.reseau.*
import fr.izquierdo.phototheque.ui.Reglages
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.InputStream

class OrchestrateurTest {

    private fun media(instant: Double, nom: String = "a.jpg") =
        Media(instant.toLong(), "DCIM/Camera", nom, 10L, instant)

    /** Serveur simule : on programme le resultat de chaque envoi. */
    private class FauxServeur(
        val horizons: Map<String, Double> = emptyMap(),
        val reclame: (List<FichierPlan>) -> List<String> = { f -> f.map { it.hash } },
        val resultats: MutableList<ResultatEnvoi> = mutableListOf(),
        /** Chemins pour lesquels `envoyer` echoue systematiquement, quel que
         *  soit le contenu de `resultats` : les deux mecanismes ne se genent
         *  pas, les anciens tests ne posant jamais celui-ci. */
        val echouerSur: Set<String> = emptySet(),
        /** Bilans a renvoyer par commit successif, dans l'ordre des paquets ;
         *  epuise, retombe sur un commit neutre. */
        val bilansCommit: MutableList<Map<String, Double>> = mutableListOf(),
    ) : Serveur {
        var horizonsEnvoyes: Map<String, Double>? = null
        var commitAppele = false
        /** Un element par appel a `commit` : l'orchestrateur en fait un par
         *  paquet, la ou l'ancien code n'en faisait qu'un pour toute la
         *  synchronisation. */
        val commits = mutableListOf<Map<String, Double>>()
        /** Les sessions que l'orchestrateur a demande d'oublier, suite a une
         *  interruption en cours de paquet. */
        val abandons = mutableListOf<String>()
        private var n = 0
        override fun horizon() = ReponseHorizon(null, horizons)
        override fun plan(f: List<FichierPlan>) = ReponsePlan("%032x".format(++n), reclame(f))
        /** Les empreintes vues par le serveur, dans l'ordre : elles doivent
         *  etre celles que le plan a annoncees, jamais recalculees. */
        val empreintesRecues = mutableListOf<String>()
        override fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long,
                             empreinteAttendue: String): ResultatEnvoi {
            empreintesRecues += empreinteAttendue
            if (chemin in echouerSur) return ResultatEnvoi.ECHEC
            return if (resultats.isEmpty()) ResultatEnvoi.OK else resultats.removeAt(0)
        }
        override fun commit(session: String, horizons: Map<String, Double>): Map<String, Double> {
            horizonsEnvoyes = horizons; commitAppele = true; commits += horizons
            return if (bilansCommit.isEmpty()) mapOf("sorted" to 1.0) else bilansCommit.removeAt(0)
        }
        override fun abandonner(session: String) { abandons += session }
    }

    private class FausseSource(val medias: List<Media>) : SourceMedias {
        override fun lister() = medias
        override fun ouvrir(media: Media): InputStream = "contenu".byteInputStream()
    }

    @Test fun cas_nominal_tout_est_envoye_et_l_horizon_avance() {
        val serveur = FauxServeur()
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0), media(200.0))), serveur)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(2, bilan.envoyes)
        assertEquals(mapOf("DCIM/Camera" to 200.0), serveur.horizonsEnvoyes)
    }

    @Test fun l_empreinte_passee_a_l_envoi_est_celle_annoncee_au_plan() {
        // Le serveur renvoie l'empreinte du fichier TEL QUE RECU et le client la
        // compare : encore faut-il qu'il compare a celle que le plan a annoncee.
        // La recalculer au moment de l'envoi rendrait la verification circulaire
        // et laisserait passer un transfert abime.
        val serveur = FauxServeur()
        Orchestrateur(FausseSource(listOf(media(100.0))), serveur)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        val attendue = fr.izquierdo.phototheque.medias.Empreintes
            .sha256("contenu".byteInputStream())
        assertEquals(listOf(attendue), serveur.empreintesRecues)
    }

    @Test fun un_echec_au_milieu_arrete_l_horizon_avant_lui() {
        val serveur = FauxServeur(resultats = mutableListOf(
            ResultatEnvoi.OK, ResultatEnvoi.ECHEC, ResultatEnvoi.OK))
        val bilan = Orchestrateur(
            FausseSource(listOf(media(100.0), media(200.0), media(300.0))), serveur)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
        assertEquals(1, bilan.echecs)
    }

    @Test fun le_commit_est_appele_MEME_apres_un_echec() {
        // Sans cela les fichiers deja recus resteraient indefiniment dans le
        // depot temporaire du NUC, sans que rien ne les range.
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.ECHEC))
        Orchestrateur(FausseSource(listOf(media(100.0))), serveur)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertTrue(serveur.commitAppele)
    }

    @Test fun une_extension_refusee_ne_compte_pas_comme_un_echec() {
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.EXTENSION_REFUSEE))
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0, "a.webm"))), serveur)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(0, bilan.echecs)
        assertEquals(1, bilan.refuses)
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
    }

    @Test fun une_revocation_arrete_tout_immediatement() {
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.REVOQUE))
        val bilan = Orchestrateur(
            FausseSource(listOf(media(100.0), media(200.0))), serveur)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertTrue(bilan.revoque)
        assertEquals(0, bilan.envoyes)
    }

    @Test fun les_medias_deja_connus_ne_sont_pas_envoyes() {
        // Le serveur ne reclame rien : on ne transfere rien, mais on valide
        // quand meme pour faire avancer l'horizon.
        val serveur = FauxServeur(reclame = { emptyList() })
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0))), serveur)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(0, bilan.envoyes)
        assertTrue(serveur.commitAppele)
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
    }

    @Test fun un_media_illisible_ne_fait_pas_echouer_la_synchro_ni_perdre_le_commit() {
        // Cas banal : la photo a ete supprimee entre le listing et l'envoi.
        // Sans filet, l'exception remontait hors de synchroniser() et le commit
        // n'avait jamais lieu — les fichiers deja recus restaient bloques pour
        // toujours dans le depot temporaire du NUC.
        val bavard = media(100.0)
        val muet = media(200.0, "disparu.jpg")
        val source = object : SourceMedias {
            override fun lister() = listOf(bavard, muet)
            override fun ouvrir(media: Media): InputStream =
                if (media.nom == "disparu.jpg") throw java.io.FileNotFoundException(media.nom)
                else "contenu".byteInputStream()
        }
        val serveur = FauxServeur()

        val bilan = Orchestrateur(source, serveur)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))

        assertTrue("le commit doit avoir lieu malgre le media illisible", serveur.commitAppele)
        assertEquals(1, bilan.envoyes)
        assertEquals(1, bilan.echecs)
        // L'horizon ne doit PAS passer par-dessus le media illisible.
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
    }

    @Test fun un_media_illisible_bloque_l_horizon_de_son_dossier() {
        // Le media a 100 est illisible des le calcul d'empreinte, celui a 200
        // part sans probleme, tous deux dans le MEME dossier. Si l'illisible
        // etait simplement omis de `envois`, l'horizon sauterait a 200 et le
        // media a 100 ne serait PLUS JAMAIS propose — perte definitive et
        // silencieuse. Le dossier doit donc rester bloque.
        val perdu = media(100.0, "disparu.jpg")
        val bon = media(200.0)
        val source = object : SourceMedias {
            override fun lister() = listOf(perdu, bon)
            override fun ouvrir(media: Media): InputStream =
                if (media.nom == "disparu.jpg") throw java.io.FileNotFoundException(media.nom)
                else "contenu".byteInputStream()
        }
        val serveur = FauxServeur()

        Orchestrateur(source, serveur).synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))

        assertTrue("le commit doit avoir lieu", serveur.commitAppele)
        assertFalse(
            "l'horizon a saute par-dessus un media illisible : il est perdu",
            "DCIM/Camera" in serveur.horizonsEnvoyes!!)
    }

    // --- Decoupage en paquets, horizon gele entre paquets, interruption ---

    @Test fun chaque_paquet_est_valide_par_son_propre_commit() {
        // Trois medias de 400 octets, paquets de 1000 : deux tiennent
        // ensemble (800), le troisieme fait son propre paquet -> 2 paquets,
        // 2 commits. (600 octets ne conviendrait pas ici : deux medias de 600
        // depassent deja 1000 a eux seuls, ce qui forcerait un paquet par
        // media et romprait l'intention du test.)
        val medias = (1L..3L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 400, it.toDouble() * 1000)
        }
        val serveur = FauxServeur()
        val bilan = Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(2, serveur.commits.size)
        assertEquals(3, bilan.envoyes)
    }

    @Test fun un_echec_au_premier_paquet_gele_le_dossier_pour_les_suivants() {
        // LE test qui protege les photos. Le media 1 echoue a l'envoi ; les
        // medias 2 et 3, chacun dans un paquet suivant (600 octets chacun,
        // paquets de 1000 : un seul media par paquet), reussissent.
        // L'horizon de DCIM/Camera ne doit JAMAIS etre transmis, sinon le
        // media 1 ne sera plus jamais propose par le serveur.
        val medias = (1L..3L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = FauxServeur(echouerSur = setOf("DCIM/Camera/m1.jpg"))
        val bilan = Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertTrue("aucun commit ne doit porter d'horizon pour ce dossier",
            serveur.commits.none { it.containsKey("DCIM/Camera") })
        // Un dossier gele n'interrompt PAS le reste : sans cette assertion, un
        // code qui arreterait toute la synchro au premier echec passerait
        // aussi ce test alors qu'il viole la spec.
        assertEquals(2, bilan.envoyes)
    }

    @Test fun un_rangement_rate_par_le_serveur_gele_le_dossier_pour_les_suivants() {
        // LE test qui protege les photos contre le decoupage en paquets.
        //
        // Quand son tri echoue, le serveur n'ecrit AUCUN horizon -- mais il a
        // DEJA detruit le fichier fautif (app.py : le nettoyage de la session
        // s'execute avant le test sur `errors`, et mediasort n'efface pas ce
        // qu'il n'a pas su ranger). L'application, elle, n'a rien constate :
        // tous ses envois ont recu un 200, donc `Horizons.calculer` ne gele
        // rien. Si un paquet suivant du meme dossier faisait avancer
        // l'horizon, le media detruit passerait dessous : il n'existe plus
        // nulle part et ne sera PLUS JAMAIS propose.
        val medias = (1L..2L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = FauxServeur(bilansCommit = mutableListOf(
            mapOf("sorted" to 0.0, "errors" to 1.0),
            mapOf("sorted" to 1.0, "errors" to 0.0),
        ))
        Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        // Sans cette assertion, un code qui s'arreterait au premier paquet
        // passerait le test suivant sans rien prouver.
        assertEquals("deux paquets, donc deux commits", 2, serveur.commits.size)
        // Le PREMIER commit porte forcement l'horizon : l'application ne peut
        // pas deviner que le tri va echouer. C'est a partir du deuxieme que la
        // perte se joue.
        assertTrue("un horizon transmis apres un rangement rate fait passer " +
                   "le media detruit sous l'horizon : perte definitive",
                   serveur.commits.drop(1).none { it.containsKey("DCIM/Camera") })
    }

    @Test fun un_rangement_REUSSI_ne_gele_aucun_dossier() {
        // Le pendant du test precedent : geler sans regarder `errors` serait
        // tout aussi faux, l'horizon ne bougerait plus jamais au-dela du
        // premier paquet et chaque synchro reproposerait toute la
        // bibliotheque.
        val medias = (1L..2L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = FauxServeur()
        Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(2, serveur.commits.size)
        assertEquals(mapOf("DCIM/Camera" to 2000.0), serveur.commits[1])
    }

    @Test fun un_dossier_sain_avance_malgre_l_echec_d_un_autre() {
        val medias = listOf(
            Media(1, "DCIM/Camera", "m1.jpg", 600, 1000.0),
            Media(2, "Pictures/WhatsApp", "w2.jpg", 600, 2000.0),
        )
        val serveur = FauxServeur(echouerSur = setOf("DCIM/Camera/m1.jpg"))
        Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera", "Pictures/WhatsApp")))
        assertTrue(serveur.commits.any { it.containsKey("Pictures/WhatsApp") })
    }

    @Test fun une_interruption_arrete_net_et_garde_les_paquets_valides() {
        // 600 octets par media, paquets de 1000 : un seul media par paquet.
        // Le premier appel a `interrompu` sert la verification du paquet 1,
        // le second l'envoi de son unique media (les deux doivent laisser
        // passer pour que ce paquet se termine et soit valide) ; le
        // troisieme, celui qui arrete tout, doit tomber PENDANT le paquet 2
        // (sur l'envoi de son media) et non avant lui, sinon le serveur
        // n'aurait jamais de session a abandonner (voir le test suivant).
        val medias = (1L..4L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = FauxServeur()
        var appels = 0
        val bilan = Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")), interrompu = { appels++ >= 3 })
        assertTrue(bilan.interrompu)
        // Exactement 1 : `isNotEmpty` passerait aussi si le paquet abandonne
        // avait ete commite lui aussi, ce que la spec interdit.
        assertEquals(1, serveur.commits.size)
    }

    @Test fun une_interruption_previent_le_serveur_du_paquet_abandonne() {
        val medias = (1L..4L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = FauxServeur()
        var appels = 0
        Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")), interrompu = { appels++ >= 3 })
        assertTrue(serveur.abandons.isNotEmpty())
    }

    @Test fun l_avancement_est_publie_avec_la_destination_prevue() {
        val medias = listOf(
            Media(1, "DCIM/Camera", "v.mp4", 600, 1759000102.0, estVideo = true))
        val vus = mutableListOf<Avancement>()
        Orchestrateur(FausseSource(medias), FauxServeur(), taillePaquet = 1000,
                      surAvancement = { vus += it })
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertTrue("une phase d'analyse doit etre publiee",
                   vus.any { it.phase == Phase.ANALYSE })
        assertTrue("la destination prevue doit apparaitre",
            vus.any { it.destinationPrevue == "Videos/2025/09 SEPTEMBRE" })
    }

    @Test fun l_avancement_final_annonce_le_total_en_octets() {
        val medias = (1L..3L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val vus = mutableListOf<Avancement>()
        Orchestrateur(FausseSource(medias), FauxServeur(), taillePaquet = 1000,
                      surAvancement = { vus += it })
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(1800L, vus.last().octetsTotal)
        // `octetsTotal` est fige au debut et ne bouge jamais : sans cette
        // assertion sur `octetsFaits`, le test passerait meme si la
        // progression reelle (fichiersFaits++/octetsFaits+=) disparaissait.
        assertEquals(1800L, vus.last().octetsFaits)
    }

    // --- Revocation vs interruption, cumul du bilan serveur, progression ---

    @Test fun une_revocation_n_est_pas_annoncee_comme_une_interruption_utilisateur() {
        // Le serveur repond REVOQUE au paquet 1 ; il y a un paquet 2 ensuite
        // pour que le test passe par la verification de TETE de la boucle des
        // paquets (`if (revoque) break`), pas par le court-circuit interne a
        // la boucle d'envoi. Les deux pannes doivent produire deux messages
        // distincts a l'ecran : les confondre annoncerait "arret demande"
        // pour un appareil revoque.
        val medias = (1L..2L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.REVOQUE))
        val bilan = Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertTrue(bilan.revoque)
        assertFalse("une revocation n'est pas une interruption utilisateur",
                    bilan.interrompu)
    }

    @Test fun le_bilan_serveur_cumule_les_commits_au_lieu_de_les_ecraser() {
        // Avec N commits, ne garder que le dernier ferait declarer reussie
        // une synchro dont un paquet a echoue au rangement :
        // EtatSynchro.estUneReussite ne regarde que la valeur finale de
        // "errors".
        val medias = (1L..2L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = FauxServeur(bilansCommit = mutableListOf(
            mapOf("sorted" to 1.0, "errors" to 1.0),
            mapOf("sorted" to 1.0, "errors" to 0.0),
        ))
        val bilan = Orchestrateur(FausseSource(medias), serveur, taillePaquet = 1000)
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(1.0, bilan.bilanServeur["errors"])
    }

    @Test fun un_rattrapage_ancien_n_efface_pas_la_memoire_des_synchros_recentes() {
        // Le serveur connaît déjà septembre 2026 ; le rattrapage ne contient
        // que du 2021. Sans la monotonie (tâche 6), le commit renverrait
        // 2021 et le serveur ÉCRASERAIT la mémoire de 2026 : la nuit
        // suivante, cinq ans de médias seraient reproposés, relus, et
        // rejetés un par un par l'anti-doublon.
        val vieux = media(1_609_459_200.0)                 // 01/01/2021
        val serveur = FauxServeur(horizons = mapOf("DCIM/Camera" to 1_789_000_000.0))

        Orchestrateur(FausseSource(listOf(vieux)), serveur).synchroniser(
            Reglages(dossiersSeuls = setOf("DCIM/Camera"), debutJour = "2020-01-01"))

        assertEquals(1_789_000_000.0,
                     serveur.commits.last().getValue("DCIM/Camera"), 0.001)
    }

    @Test fun la_borne_basse_de_la_fenetre_gele_l_horizon_du_dossier_ampute() {
        // LE test qui protege les photos contre la fenetre de dates.
        //
        // Le dossier est DEJA connu du serveur, horizon a la mi-decembre 2020.
        // L'utilisateur remonte sa date de debut au 01/01/2021 (geste prevu
        // par la spec §4.1). `Selection.candidats` prend soin de partir de
        // l'horizon -- il ne remonte JAMAIS un plancher -- donc le media du
        // 21/12/2020 est bien candidat ; c'est la borne basse de la fenetre
        // qui l'ecarte ensuite.
        //
        // Si l'horizon avancait quand meme sur le media de mai 2021, la
        // tranche [horizon, debut[ passerait DESSOUS : le serveur ne la
        // reproposerait plus jamais, meme apres avoir rebaisse la date. Des
        // photos perdues, en silence.
        val gap = Media(1, "DCIM/Camera", "decembre.jpg", 10, 1_608_500_000.0)
        val dedans = Media(2, "DCIM/Camera", "mai.jpg", 10, 1_620_000_000.0)
        val serveur = FauxServeur(horizons = mapOf("DCIM/Camera" to 1_608_000_000.0))

        val bilan = Orchestrateur(FausseSource(listOf(gap, dedans)), serveur).synchroniser(
            Reglages(dossiersSeuls = setOf("DCIM/Camera"),
                     debutJour = "2021-01-01", debutApplique = "2021-01-01"))

        // Le media de la fenetre part bien : geler l'horizon ne doit pas
        // arreter la sauvegarde elle-meme.
        assertEquals(1, bilan.envoyes)
        assertTrue("un horizon transmis ici fait passer la tranche ecartee " +
                   "sous l'horizon : perte definitive et silencieuse",
                   serveur.commits.none { it.containsKey("DCIM/Camera") })
    }

    @Test fun la_borne_HAUTE_de_la_fenetre_ne_gele_rien() {
        // Le pendant du test precedent. Geler sur la borne haute serait tout
        // aussi faux : un horizon calcule sur les seuls medias envoyes ne peut
        // pas depasser la date de fin, il n'y a donc aucune tranche a
        // proteger. Geler quand meme figerait l'horizon de tout rattrapage
        // ferme par une date de fin -- c'est-a-dire de tous.
        val dedans = Media(1, "DCIM/Camera", "juin.jpg", 10, 1_622_500_000.0)
        val apres = Media(2, "DCIM/Camera", "aout.jpg", 10, 1_630_000_000.0)
        val serveur = FauxServeur()

        Orchestrateur(FausseSource(listOf(dedans, apres)), serveur).synchroniser(
            Reglages(dossiersSeuls = setOf("DCIM/Camera"),
                     debutJour = "2021-01-01", debutApplique = "2021-01-01",
                     finJour = "2021-07-01"))

        assertEquals(mapOf("DCIM/Camera" to 1_622_500_000.0), serveur.horizonsEnvoyes)
    }

    @Test fun la_date_de_debut_sert_de_plancher_meme_sans_ordre_de_reprise_actif() {
        // Rôle DISTINCT de l'ordre de reprise ponctuel (Selection.plancherReprise) :
        // la date de début est aussi le plancher PERMANENT des dossiers sans
        // horizon (spec §4.2 règle 2). Ici la reprise a DÉJÀ été menée à son
        // terme (debutApplique = debutJour), donc seul ce rôle permanent est
        // en jeu -- le serveur, lui, ne connaît aucun `depuis`.
        val vieux = media(100.0)
        val recent = media(2_000_000_000.0)
        val serveur = FauxServeur()

        val bilan = Orchestrateur(FausseSource(listOf(vieux, recent)), serveur).synchroniser(
            Reglages(dossiersSeuls = setOf("DCIM/Camera"),
                     debutJour = "2020-01-01", debutApplique = "2020-01-01"))

        assertEquals(1, bilan.envoyes)
        // C'est CETTE assertion qui rend le test discriminant, pas le compte
        // d'envois : supprimer le role de plancher laisserait de toute facon
        // le media de 1970 dehors -- la borne basse de la fenetre l'ecarterait
        // a elle seule -- et le compte resterait a 1. Mais il deviendrait un
        // media ECARTE PAR LE BAS, ce qui gele le dossier (voir
        // `la_borne_basse_de_la_fenetre_gele_l_horizon_du_dossier_ampute`) :
        // plus aucun horizon ne serait transmis, et l'horizon de ce dossier
        // n'avancerait plus jamais.
        assertEquals(mapOf("DCIM/Camera" to 2_000_000_000.0), serveur.horizonsEnvoyes)
    }

    @Test fun un_media_illisible_fait_quand_meme_progresser_la_barre() {
        // Un echec d'ENVOI avance fichiersFaits/octetsFaits ; un echec de
        // LECTURE (media supprime entre le listing et l'envoi, cas banal sur
        // un telephone) doit faire pareil, sinon la barre reste bloquee sous
        // 100% pour toujours — un mensonge sur l'ecran meme que ce lot existe
        // pour rendre honnete.
        val bavard = Media(1, "DCIM/Camera", "a.jpg", 600, 100.0)
        val muet = Media(2, "DCIM/Camera", "disparu.jpg", 600, 200.0)
        val source = object : SourceMedias {
            override fun lister() = listOf(bavard, muet)
            override fun ouvrir(media: Media): InputStream =
                if (media.nom == "disparu.jpg") throw java.io.FileNotFoundException(media.nom)
                else "contenu".byteInputStream()
        }
        val vus = mutableListOf<Avancement>()
        Orchestrateur(source, FauxServeur(), taillePaquet = 1000,
                      surAvancement = { vus += it })
            .synchroniser(Reglages(dossiersSeuls = setOf("DCIM/Camera")))
        assertEquals(1200L, vus.last().octetsFaits)
    }
}
