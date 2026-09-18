package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Trois unités pour la même notion : DATE_TAKEN en millisecondes (parfois
 * absent), DATE_MODIFIED en secondes, et le serveur qui attend des secondes
 * flottantes. Se tromper d'un facteur 1000 fait avancer un horizon de
 * trente ans et perd tout le dossier, définitivement et en silence.
 */
class DatesTest {

    @Test fun date_de_prise_de_vue_convertie_en_secondes() {
        // 2026-09-12 14:30:00 UTC = 1789223400 s = 1789223400000 ms
        assertEquals(1789223400.0, Dates.instantSecondes(1789223400000L, 0L), 0.001)
    }

    @Test fun date_de_prise_de_vue_absente_on_prend_la_date_de_modification() {
        assertEquals(1789223400.0, Dates.instantSecondes(null, 1789223400L), 0.001)
    }

    @Test fun date_de_prise_de_vue_a_zero_compte_comme_absente() {
        // MediaStore renvoie 0 et non null quand la métadonnée manque.
        assertEquals(1789223400.0, Dates.instantSecondes(0L, 1789223400L), 0.001)
    }

    @Test fun les_millisecondes_ne_sont_pas_perdues() {
        assertEquals(1789223400.5, Dates.instantSecondes(1789223400500L, 0L), 0.001)
    }
}
