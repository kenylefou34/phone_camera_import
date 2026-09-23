package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReglagesTest {

    @Test fun cocher_auto_efface_la_date_de_fin() {
        // C'est la seule protection fiable contre la date de fin oubliée : un
        // compteur « 342 médias hors fenêtre » se remarque une semaine, pas
        // six mois.
        val avant = Reglages(debutJour = "2019-01-01", finJour = "2020-12-31")

        val apres = avant.enAuto()

        assertTrue(apres.auto)
        assertNull(apres.finJour)
        assertEquals("2019-01-01", apres.debutJour)   // la borne basse reste
    }

    @Test fun les_reglages_survivent_a_un_aller_retour_par_json() {
        val reglages = Reglages(
            dossiersSeuls = setOf("DCIM/Camera"),
            dossiersRecursifs = setOf("Pictures"),
            debutJour = "2026-09-15", finJour = null,
            debutApplique = "2026-09-15", auto = true)

        assertEquals(reglages, Reglages.depuisJson(reglages.versJson()))
    }

    @Test fun un_json_absent_donne_les_trois_dossiers_historiques() {
        // Une mise à jour de l'application ne doit RIEN changer à ce qui est
        // sauvegardé tant que l'utilisateur n'a rien choisi.
        assertEquals(Reglages.DEFAUT, Reglages.depuisJson(null))
        assertEquals(
            setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"),
            Reglages.DEFAUT.dossiersSeuls)
    }

    @Test fun un_json_illisible_ne_fait_pas_planter_et_retombe_sur_le_defaut() {
        // Préférences corrompues, rétrogradage de version : lever ici fermerait
        // l'application à CHAQUE lancement, définitivement.
        assertEquals(Reglages.DEFAUT, Reglages.depuisJson("{ceci n'est pas du json"))
    }

    @Test fun une_reprise_deja_menee_a_son_terme_ne_se_rejoue_pas() {
        // Le bogue que cette marque existe pour empêcher : sans la comparaison,
        // chaque nuit reproposerait tous les vieux médias.
        assertTrue(Reglages(debutJour = "2019-01-01").repriseADemander())
        assertFalse(Reglages(debutJour = "2019-01-01",
                             debutApplique = "2019-01-01").repriseADemander())
        assertTrue(Reglages(debutJour = "2018-01-01",
                            debutApplique = "2019-01-01").repriseADemander())
    }

    // --- Reglages.apresSynchro : les quatre combinaisons vus vide/non vide x
    // reussiteComplete vrai/faux. Extraite de TravailSynchro pour être
    // testable sur la JVM : ce projet n'a aucun test d'instrumentation
    // Android pour la couvrir autrement.

    @Test fun apres_synchro_incomplete_sans_rien_avoir_vu_ne_change_rien() {
        val avant = Reglages(dossiersConnus = setOf("DCIM/Camera"),
                             debutJour = "2020-01-01", debutApplique = null)

        val apres = avant.apresSynchro(vus = emptySet(), reussiteComplete = false,
                                       debutJourEnCours = "2020-01-01")

        assertEquals(avant, apres)
    }

    @Test fun apres_synchro_reussie_sans_rien_avoir_vu_ne_consomme_pas_la_reprise() {
        // Le constat du relecteur : une synchro peut « réussir » sans avoir
        // rien vu (aucun dossier coché n'existe sur ce téléphone, ou -- cas le
        // plus insidieux -- un accès PARTIEL, que l'appelant doit déjà avoir
        // retiré de `reussiteComplete` avant d'arriver ici). La reprise n'a
        // alors jamais été tentée : la consommer perdrait les vieux médias
        // pour de bon dès l'accès complet accordé.
        val avant = Reglages(dossiersConnus = setOf("DCIM/Camera"),
                             debutJour = "2020-01-01", debutApplique = null)

        val apres = avant.apresSynchro(vus = emptySet(), reussiteComplete = true,
                                       debutJourEnCours = "2020-01-01")

        assertEquals(avant, apres)
    }

    @Test fun apres_synchro_incomplete_range_quand_meme_les_dossiers_vus() {
        // Contrairement à `debutApplique`, `dossiersConnus` ne dépend pas de
        // la réussite : il décrit ce qui EST visible sur le téléphone, pas ce
        // que la synchro a accompli.
        val avant = Reglages(dossiersConnus = setOf("DCIM/Camera"),
                             debutJour = "2020-01-01", debutApplique = null)

        val apres = avant.apresSynchro(vus = setOf("DCIM/Camera", "Pictures/WhatsApp"),
                                       reussiteComplete = false, debutJourEnCours = "2020-01-01")

        assertEquals(setOf("DCIM/Camera", "Pictures/WhatsApp"), apres.dossiersConnus)
        assertNull(apres.debutApplique)
    }

    @Test fun apres_synchro_reussie_range_les_deux_champs() {
        val avant = Reglages(debutJour = "2020-01-01", debutApplique = null)

        val apres = avant.apresSynchro(vus = setOf("DCIM/Camera"), reussiteComplete = true,
                                       debutJourEnCours = "2020-01-01")

        assertEquals(setOf("DCIM/Camera"), apres.dossiersConnus)
        assertEquals("2020-01-01", apres.debutApplique)
    }
}
