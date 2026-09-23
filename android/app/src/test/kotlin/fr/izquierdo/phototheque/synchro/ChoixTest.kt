package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.ui.Reglages
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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

    // --- dossiersASauvegarder : la synchro lit les reglages, pas une constante ---

    @Test fun les_dossiers_synchronises_viennent_des_reglages_et_non_de_la_constante() {
        val reglages = Reglages(dossiersSeuls = setOf("Pictures/Messages"))

        val choisis = Choix.dossiersASauvegarder(
            reglages, tous = setOf("Pictures/Messages", "DCIM/Camera"))

        assertEquals(setOf("Pictures/Messages"), choisis)
    }

    @Test fun des_reglages_vierges_sauvegardent_les_trois_dossiers_historiques() {
        // Une mise à jour ne doit RIEN changer tant que l'utilisateur n'a pas
        // ouvert l'écran.
        val choisis = Choix.dossiersASauvegarder(
            Reglages.DEFAUT,
            tous = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp", "Download"))

        assertEquals(setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"), choisis)
    }

    @Test fun une_coche_recursive_des_reglages_embarque_bien_la_descendance() {
        // Ce test attrape l'interversion des deux ensembles : avec
        // `dossiersSeuls` et `dossiersRecursifs` échangés, seul « Pictures »
        // sortirait. Aucun autre test ne le voit, parce qu'aucun autre jeu de
        // données ne contient de sous-dossier d'un dossier sélectionné.
        val choisis = Choix.dossiersASauvegarder(
            Reglages(dossiersRecursifs = setOf("Pictures")),
            tous = setOf("Pictures", "Pictures/WhatsApp", "DCIM/Camera"))

        assertEquals(setOf("Pictures", "Pictures/WhatsApp"), choisis)
    }

    // --- introuvables : l'alerte rouge ne doit pas crier sur une coche récursive normale ---

    @Test fun un_dossier_coche_recursif_present_par_ses_enfants_seulement_n_est_pas_introuvable() {
        // MediaStore ne rend jamais "Pictures" lui-même s'il n'a aucun média
        // DIRECT : seul "Pictures/WhatsApp" apparaît dans vus. Une comparaison
        // par égalité stricte crierait "introuvable" sur une configuration qui
        // sauvegarde pourtant parfaitement.
        val reglages = Reglages(dossiersRecursifs = setOf("Pictures"))

        val introuvables = Choix.introuvables(reglages, vus = setOf("Pictures/WhatsApp"))

        assertEquals(emptySet<String>(), introuvables)
    }

    @Test fun un_dossier_coche_absent_partout_est_introuvable() {
        val reglages = Reglages(dossiersRecursifs = setOf("Pictures"))

        val introuvables = Choix.introuvables(reglages, vus = setOf("DCIM/Camera"))

        assertEquals(setOf("Pictures"), introuvables)
    }

    @Test fun un_dossier_coche_seulement_sans_media_direct_est_introuvable() {
        // Symétrique du test précédent, côté "seuls" : "Pictures" coché
        // "ce dossier seulement" (pas récursif) ne sauvegarde JAMAIS
        // "Pictures/WhatsApp" (Choix.resoudre compare `seuls` par égalité
        // stricte). Contrairement à la coche récursive, ce choix précis ne
        // sauvegarde structurellement rien ici, et doit être signalé.
        val reglages = Reglages(dossiersSeuls = setOf("Pictures"))

        val introuvables = Choix.introuvables(reglages, vus = setOf("Pictures/WhatsApp"))

        assertEquals(setOf("Pictures"), introuvables)
    }

    // --- HERITEE : un enfant d'une coche récursive est sauvegardé, mais pas par lui-même ---

    @Test fun l_etat_d_un_enfant_dont_un_ancetre_est_recursif_est_herite() {
        val feuille = Noeud("Pictures/WhatsApp", "WhatsApp", 10, 10, emptyList())

        assertEquals(Coche.HERITEE, Choix.etat(feuille, emptySet(), setOf("Pictures")))
    }

    // --- PARTIELLE sur trois niveaux, et « Ne pas sauvegarder » qui fait
    // vraiment quelque chose ---

    /** Trois niveaux : « Pictures » > « Pictures/App » > « Pictures/App/Sent ». */
    private fun arbreATroisNiveaux(): Noeud {
        val petitFils = Noeud("Pictures/App/Sent", "Sent", 5, 5, emptyList())
        val fils = Noeud("Pictures/App", "App", 0, 5, listOf(petitFils))
        return Noeud("Pictures", "Pictures", 0, 5, listOf(fils))
    }

    @Test fun un_petit_fils_coche_rend_le_grand_pere_partiel() {
        // La recursion n'etait verifiee qu'a UN niveau. S'arreter aux enfants
        // directs afficherait une case vide sur « Pictures » alors que sa
        // descendance part : on croirait le dossier hors sauvegarde.
        val racine = arbreATroisNiveaux()

        assertEquals(Coche.PARTIELLE,
                     Choix.etat(racine, setOf("Pictures/App/Sent"), emptySet()))
        assertEquals(listOf("Pictures/App/Sent"),
                     Choix.descendantsCoches(racine, setOf("Pictures/App/Sent"), emptySet()))
    }

    @Test fun les_descendants_coches_sont_nommes_a_tous_les_niveaux() {
        // Ce sont eux que l'ecran affiche avant de proposer « Ne pas
        // sauvegarder » : decocher toute une descendance sans dire laquelle
        // serait une surprise.
        val racine = arbreATroisNiveaux()

        assertEquals(listOf("Pictures/App", "Pictures/App/Sent"),
                     Choix.descendantsCoches(
                         racine, setOf("Pictures/App/Sent"), setOf("Pictures/App")))
    }

    @Test fun ne_pas_sauvegarder_sur_un_dossier_a_moitie_coche_decoche_la_descendance() {
        // LE defaut que ce correctif supprime : sur un noeud PARTIELLE,
        // retirer le seul chemin -- qui n'est dans aucun des deux ensembles --
        // ne faisait RIEN. L'utilisateur croyait avoir exclu le dossier, la
        // case restait a moitie pleine, et l'enfant continuait de partir.
        val avant = Reglages(dossiersSeuls = setOf("Pictures/App/Sent", "DCIM/Camera"),
                             dossiersRecursifs = setOf("Pictures/App"))

        val apres = Choix.apresCoche(avant, "Pictures", Coche.AUCUNE)

        assertEquals(setOf("DCIM/Camera"), apres.dossiersSeuls)
        assertEquals(emptySet<String>(), apres.dossiersRecursifs)
        // Le voisin homonyme n'est pas emporte : « Pictures » ne couvre pas
        // « PicturesBis ».
        assertEquals(setOf("PicturesBis"),
                     Choix.apresCoche(Reglages(dossiersSeuls = setOf("PicturesBis")),
                                      "Pictures", Coche.AUCUNE).dossiersSeuls)
    }

    @Test fun cocher_un_dossier_n_efface_pas_les_choix_de_sa_descendance() {
        // Le pendant du test precedent : propager la coche, elle, effacerait
        // en silence trois sous-dossiers choisis un par un la semaine
        // derniere. Seul « Ne pas sauvegarder » emporte le sous-arbre.
        val avant = Reglages(dossiersSeuls = setOf("Pictures/App/Sent"))

        val apres = Choix.apresCoche(avant, "Pictures", Coche.RECURSIVE)

        assertEquals(setOf("Pictures/App/Sent"), apres.dossiersSeuls)
        assertEquals(setOf("Pictures"), apres.dossiersRecursifs)
    }

    @Test fun un_dossier_bascule_d_une_coche_a_l_autre_ne_reste_pas_dans_les_deux() {
        val apres = Choix.apresCoche(
            Reglages(dossiersSeuls = setOf("Pictures")), "Pictures", Coche.RECURSIVE)

        assertEquals(emptySet<String>(), apres.dossiersSeuls)
        assertEquals(setOf("Pictures"), apres.dossiersRecursifs)
    }

    @Test fun un_dossier_recursif_pour_lui_meme_n_a_pas_de_parent_recursif() {
        // "Pictures" est RECURSIVE pour lui-même (Choix.etat le dit déjà) :
        // il n'est pas son propre ancêtre, donc pas HERITEE.
        assertNull(Choix.parentRecursif("Pictures", setOf("Pictures")))
    }

    @Test fun le_parent_recursif_le_plus_proche_est_designe() {
        // "Pictures" ET "Pictures/WhatsApp" sont tous deux cochés en
        // récursif : c'est le plus proche qui doit être nommé à l'écran, pas
        // le premier trouvé.
        val ancetre = Choix.parentRecursif(
            "Pictures/WhatsApp/Sent", setOf("Pictures", "Pictures/WhatsApp"))

        assertEquals("Pictures/WhatsApp", ancetre)
    }
}
