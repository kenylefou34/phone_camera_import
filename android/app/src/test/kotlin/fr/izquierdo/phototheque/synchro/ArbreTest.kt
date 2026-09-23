package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

class ArbreTest {

    @Test fun les_chemins_plats_deviennent_un_arbre() {
        val arbre = Arbre.construire(mapOf(
            "DCIM/Camera" to 1200,
            "Pictures/WhatsApp" to 300,
            "Pictures/Messages" to 38))

        assertEquals(listOf("DCIM", "Pictures"), arbre.map { it.libelle })
        val pictures = arbre.first { it.libelle == "Pictures" }
        assertEquals(listOf("Messages", "WhatsApp"), pictures.enfants.map { it.libelle })
        assertEquals("Pictures/Messages", pictures.enfants.first().chemin)
    }

    @Test fun le_total_remonte_les_medias_des_sous_dossiers() {
        val arbre = Arbre.construire(mapOf(
            "Pictures/WhatsApp" to 300,
            "Pictures/Messages" to 38))

        val pictures = arbre.single()
        assertEquals(0, pictures.medias)         // rien DIRECTEMENT dans Pictures
        assertEquals(338, pictures.mediasTotal)  // mais 338 en dessous
    }

    @Test fun une_chaine_sans_media_et_a_enfant_unique_est_repliee() {
        // Android/media/com.whatsapp/WhatsApp/Media fait cinq niveaux dont
        // aucun ne contient de média : descendre marche par marche dans des
        // dossiers vides n'apprend rien et coûte cinq appuis.
        val arbre = Arbre.construire(mapOf(
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images" to 900))

        val racine = arbre.single()
        assertEquals(
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images",
            racine.libelle)
        assertEquals(
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images",
            racine.chemin)
        assertEquals(900, racine.medias)
        assertEquals(emptyList<Noeud>(), racine.enfants)
    }

    @Test fun un_dossier_qui_contient_des_medias_n_est_jamais_replie() {
        // Même avec un enfant unique : on doit pouvoir cocher le parent seul.
        val arbre = Arbre.construire(mapOf(
            "DCIM" to 12,
            "DCIM/Camera" to 1200))

        val dcim = arbre.single()
        assertEquals("DCIM", dcim.libelle)
        assertEquals(12, dcim.medias)
        assertEquals(listOf("Camera"), dcim.enfants.map { it.libelle })
    }

    @Test fun une_chaine_a_enfants_multiples_n_est_pas_repliee() {
        val arbre = Arbre.construire(mapOf(
            "Android/media/a" to 1,
            "Android/media/b" to 1))

        // « Android/media » se replie (un seul enfant, aucun média), mais
        // s'arrête là : deux enfants.
        val racine = arbre.single()
        assertEquals("Android/media", racine.libelle)
        assertEquals(listOf("a", "b"), racine.enfants.map { it.libelle })
        assertEquals("Android/media/a", racine.enfants.first().chemin)
    }

    @Test fun une_liste_vide_donne_un_arbre_vide() {
        assertEquals(emptyList<Noeud>(), Arbre.construire(emptyMap()))
    }
}
