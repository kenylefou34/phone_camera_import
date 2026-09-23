package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

class ChoixTest {

    @Test fun une_coche_simple_ne_prend_que_le_dossier_lui_meme() {
        val resolus = Choix.resoudre(
            tous = setOf("Pictures", "Pictures/WhatsApp"),
            seuls = setOf("Pictures"), recursifs = emptySet())

        assertEquals(setOf("Pictures"), resolus)
    }

    @Test fun une_coche_recursive_prend_toute_la_descendance() {
        val resolus = Choix.resoudre(
            tous = setOf("Pictures", "Pictures/WhatsApp", "Pictures/WhatsApp/Sent", "DCIM"),
            seuls = emptySet(), recursifs = setOf("Pictures"))

        assertEquals(setOf("Pictures", "Pictures/WhatsApp", "Pictures/WhatsApp/Sent"), resolus)
    }

    @Test fun une_coche_recursive_n_embarque_pas_un_homonyme_voisin() {
        // « Pictures/WhatsApp » est un PRÉFIXE de « Pictures/WhatsAppBusiness »
        // sans en être le parent. Comparer les chaînes sans le séparateur
        // sauvegarderait un dossier que l'utilisateur n'a jamais coché.
        val resolus = Choix.resoudre(
            tous = setOf("Pictures/WhatsApp", "Pictures/WhatsAppBusiness"),
            seuls = emptySet(), recursifs = setOf("Pictures/WhatsApp"))

        assertEquals(setOf("Pictures/WhatsApp"), resolus)
    }

    @Test fun un_dossier_coche_puis_disparu_du_telephone_ne_casse_rien() {
        // WhatsApp désinstallée : le réglage garde un chemin que MediaStore ne
        // rend plus. On ne le propose pas, et on ne lève pas.
        val resolus = Choix.resoudre(
            tous = setOf("DCIM/Camera"),
            seuls = setOf("DCIM/Camera", "Pictures/WhatsApp"), recursifs = emptySet())

        assertEquals(setOf("DCIM/Camera"), resolus)
    }

    @Test fun les_dossiers_entres_par_recursivite_depuis_la_derniere_fois_sont_signales() {
        // Une coche récursive est une délégation dans le temps : elle prendra
        // demain des dossiers qui n'existent pas aujourd'hui. Sans ce rappel,
        // il faudrait surveiller ; avec, on est prévenu.
        val nouveaux = Choix.nouveauxParRecursivite(
            tous = setOf("Pictures/WhatsApp", "Pictures/Telegram", "DCIM/Camera"),
            connus = setOf("Pictures/WhatsApp", "DCIM/Camera"),
            recursifs = setOf("Pictures"))

        assertEquals(setOf("Pictures/Telegram"), nouveaux)
    }

    @Test fun un_dossier_neuf_hors_de_toute_coche_recursive_n_est_pas_signale() {
        // Il n'est pas sauvegardé : l'annoncer ferait croire le contraire.
        val nouveaux = Choix.nouveauxParRecursivite(
            tous = setOf("Download/Nouveau", "DCIM/Camera"),
            connus = setOf("DCIM/Camera"),
            recursifs = setOf("Pictures"))

        assertEquals(emptySet<String>(), nouveaux)
    }

    @Test fun l_etat_d_une_coche_distingue_les_quatre_cas() {
        val feuille = Noeud("Pictures/WhatsApp", "WhatsApp", 10, 10, emptyList())
        val parent = Noeud("Pictures", "Pictures", 0, 10, listOf(feuille))

        assertEquals(Coche.AUCUNE, Choix.etat(parent, emptySet(), emptySet()))
        assertEquals(Coche.DOSSIER, Choix.etat(parent, setOf("Pictures"), emptySet()))
        assertEquals(Coche.RECURSIVE, Choix.etat(parent, emptySet(), setOf("Pictures")))
        // Seul l'enfant est coché : le parent doit le DIRE, sinon on croit le
        // dossier entièrement pris alors qu'il ne l'est qu'à moitié.
        assertEquals(Coche.PARTIELLE,
                     Choix.etat(parent, setOf("Pictures/WhatsApp"), emptySet()))
    }
}
