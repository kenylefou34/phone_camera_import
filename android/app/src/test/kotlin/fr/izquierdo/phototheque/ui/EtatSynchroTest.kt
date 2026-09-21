package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import fr.izquierdo.phototheque.synchro.Bilan

/**
 * Le compteur part de la derniere synchro REUSSIE, jamais de la derniere
 * tentative : les pires pannes sont celles ou rien ne se passe, et ou il n'y a
 * donc aucun echec a signaler.
 */
class EtatSynchroTest {

    private val jour = 24 * 3600 * 1000L

    @Test fun jamais_synchronise_ne_donne_aucun_compteur() {
        assertNull(EtatSynchro.joursDepuis(maintenantMs = 10 * jour, derniereReussiteMs = null))
    }

    @Test fun compte_les_jours_entiers_ecoules() {
        assertEquals(3L, EtatSynchro.joursDepuis(10 * jour, 7 * jour))
        assertEquals(0L, EtatSynchro.joursDepuis(10 * jour, 10 * jour))
    }

    @Test fun le_seuil_d_alerte_est_a_sept_jours() {
        assertEquals(7L, EtatSynchro.SEUIL_ALERTE_JOURS)
    }

    @Test fun un_appareil_non_appaire_et_un_qr_invalide_sont_deux_etats_distincts() {
        // Sans cette distinction, l'ecran d'appairage ne saurait pas s'il doit
        // afficher un message d'erreur ou seulement l'invitation a scanner.
        val neuf = EtatSynchro()
        val refuse = EtatSynchro(qrInvalide = true)
        assertFalse(neuf.qrInvalide)
        assertTrue(refuse.qrInvalide)
        assertFalse(refuse.appaire)
    }

    @Test fun une_panne_et_un_serveur_introuvable_sont_deux_etats_distincts() {
        // C'est LE point de la vague de correction : « pas a la maison » est
        // silencieux, une vraie panne est visible. Les confondre faisait
        // afficher le meme message rassurant sur quatre pannes differentes.
        val absent = EtatSynchro(serveurIntrouvable = true)
        val panne = EtatSynchro(erreur = "connexion fermee")
        assertNull(absent.erreur)
        assertFalse(panne.serveurIntrouvable)
        assertEquals("connexion fermee", panne.erreur)
    }

    @Test fun un_etat_neuf_ne_signale_ni_panne_ni_permission_retiree() {
        val neuf = EtatSynchro()
        assertNull(neuf.erreur)
        assertFalse(neuf.permissionRefusee)
        assertNull("null = on n'a pas encore regarde", neuf.dossiersVus)
    }

    @Test fun un_dossier_sauvegarde_absent_du_telephone_est_reperable() {
        // Les trois dossiers sauvegardes sont codes en dur. Si l'un n'existe
        // pas ici, la synchro reussit avec ZERO media et rien ne le dit : c'est
        // la difference entre les deux ensembles qui le revele.
        val sauvegardes = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp")
        val vus = mapOf("DCIM/Camera" to 1200, "Pictures/Screenshots" to 40)
        assertEquals(setOf("Pictures/WhatsApp", "Movies/WhatsApp"),
                     sauvegardes - EtatSynchro(dossiersVus = vus).dossiersVus!!.keys)
    }

    // ---- Ce qui se passe une fois la synchronisation terminee -------------

    private fun bilan(echecs: Int = 0, revoque: Boolean = false, erreursServeur: Double = 0.0) =
        Bilan(envoyes = 1, refuses = 0, echecs = echecs, revoque = revoque,
              bilanServeur = mapOf("sorted" to 1.0, "errors" to erreursServeur))

    @Test fun une_synchro_aboutie_RALLUME_le_bandeau_de_permission() {
        // L'enchainement que ce test interdit : synchroniser() eteint le
        // bandeau en partant, MediaStore rend vide sans lever, la synchro
        // "reussit" a zero media -- et l'accueil repartait au vert, sans aucun
        // bandeau, sur un telephone qui ne sauvegarde plus rien.
        val eteint = EtatSynchro(permissionRefusee = false)
        val apres = eteint.apresSynchro(bilan(), accesPartiel = false,
                                        accesRefuse = true, derniereReussiteMs = null)
        assertTrue("le bandeau doit etre rallume par l'etat d'arrivee",
                   apres.permissionRefusee)
    }

    @Test fun une_synchro_aboutie_eteint_le_bandeau_quand_l_acces_est_revenu() {
        val allume = EtatSynchro(permissionRefusee = true)
        val apres = allume.apresSynchro(bilan(), accesPartiel = false,
                                        accesRefuse = false, derniereReussiteMs = 1L)
        assertFalse(apres.permissionRefusee)
    }

    @Test fun sans_acces_aux_medias_une_synchro_a_vide_n_est_PAS_une_reussite() {
        // Sinon la date serait gravee dans Memoire, donc sur le disque, et plus
        // rien ne l'effacerait : un mensonge durable.
        assertFalse(EtatSynchro.estUneReussite(bilan(), accesRefuse = true))
    }

    @Test fun un_rangement_en_erreur_cote_serveur_n_est_pas_une_reussite() {
        // errors > 0 : le serveur n'a fait avancer AUCUN horizon.
        assertFalse(EtatSynchro.estUneReussite(bilan(erreursServeur = 2.0), accesRefuse = false))
    }

    @Test fun une_synchro_propre_est_une_reussite() {
        assertTrue(EtatSynchro.estUneReussite(bilan(), accesRefuse = false))
    }

    @Test fun un_echec_local_ou_une_revocation_ne_sont_pas_des_reussites() {
        assertFalse(EtatSynchro.estUneReussite(bilan(echecs = 1), accesRefuse = false))
        assertFalse(EtatSynchro.estUneReussite(bilan(revoque = true), accesRefuse = false))
    }
}
