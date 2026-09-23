package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class LisibleTest {

    @Test fun les_octets_se_lisent_en_francais() {
        assertEquals("512 o", Lisible.octets(512))
        assertEquals("1,0 Ko", Lisible.octets(1024))
        assertEquals("29,0 Mo", Lisible.octets(29L * 1024 * 1024))
        assertEquals("12,5 Go", Lisible.octets((12.5 * 1024 * 1024 * 1024).toLong()))
    }

    @Test fun une_duree_courte_se_dit_en_secondes() {
        assertEquals("45 s", Lisible.duree(45))
    }

    @Test fun une_duree_moyenne_se_dit_en_minutes() {
        assertEquals("18 min", Lisible.duree(18 * 60 + 20))
    }

    @Test fun une_duree_longue_se_dit_en_heures_et_minutes() {
        // Le 21/09, le rangement a pris 1 h 02 : « 62 min » serait illisible.
        assertEquals("1 h 02", Lisible.duree(62 * 60))
    }

    @Test fun une_duree_nulle_ne_dit_pas_zero_seconde() {
        assertEquals("moins d'une minute", Lisible.duree(0))
    }

    @Test fun le_temps_restant_ne_dit_pas_environ_moins_d_une_minute() {
        // L'ecran prefixait la duree d'un tilde sans regarder ce qu'elle
        // valait : « ~ moins d'une minute » se lit comme une faute de frappe.
        assertEquals("moins d'une minute", Lisible.restant(0))
        assertEquals("~ 45 s", Lisible.restant(45))
    }

    @Test fun une_courte_liste_de_noms_est_donnee_en_entier() {
        assertEquals("a, b", Lisible.enumerer(listOf("a", "b")))
        assertEquals("", Lisible.enumerer(emptyList()))
    }

    @Test fun une_longue_liste_de_noms_annonce_le_reste_sans_l_escamoter() {
        // L'« a un pres » typique : avec `noms.size` au lieu du reste, on
        // annoncerait « c et 5 autres » sur une liste de cinq.
        assertEquals("a, b, c et 2 autre(s)",
                     Lisible.enumerer(listOf("a", "b", "c", "d", "e")))
        // La limite exacte ne doit RIEN ajouter.
        assertEquals("a, b, c", Lisible.enumerer(listOf("a", "b", "c")))
    }
}
