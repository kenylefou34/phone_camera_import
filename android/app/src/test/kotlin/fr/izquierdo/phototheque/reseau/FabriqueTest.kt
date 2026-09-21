package fr.izquierdo.phototheque.reseau

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/**
 * Fabrique.client ne touche a aucune API Android : il est donc verifiable ici,
 * contrairement au reste de Decouverte.kt.
 */
class FabriqueTest {

    @Test fun aucun_client_ne_rejoue_jamais_une_requete() {
        // Le corps d'un envoi est adosse a un flux deja consomme et ferme. Si
        // OkHttp rejouait la requete, il enverrait du vide sous la taille
        // annoncee et le serveur rangerait un fichier tronque -- sans que rien
        // ne le signale, puisque la reponse serait un 200 ordinaire.
        //
        // Poser isOneShot() sur la partie fichier du multipart ne suffit pas :
        // OkHttp n'interroge que le corps de plus haut niveau. Ce drapeau-ci
        // est la seconde moitie du verrou, et celle qui couvre aussi les
        // rejeux declenches par une simple coupure de connexion.
        val avecTls = Fabrique.client(
            ChargeAppairage("https://IZQUIERDO-NUC.local:8787", "jeton", "ab".repeat(32)))
        assertFalse("client epingle", avecTls.retryOnConnectionFailure)

        // Le serveur lance a la main, sans TLS, passe par une autre branche de
        // la fabrique : elle avait ete oubliee.
        val sansTls = Fabrique.client(
            ChargeAppairage("http://192.168.1.21:8787", "jeton", null))
        assertFalse("client sans TLS", sansTls.retryOnConnectionFailure)
    }

    @Test fun les_delais_sont_poses_explicitement() {
        // Sans cela, OkHttp applique 10 s de lecture. Le 21/09, le tri d'un
        // commit a demande 1 h 02 : le telephone a raccroche au bout de dix
        // secondes, affiche « echec », et laisse le compteur sur « Jamais
        // sauvegarde » pendant que le serveur rangeait 953 medias.
        val http = Fabrique.client(ChargeAppairage("https://x:8787", "jeton", null))
        assertEquals(10_000, http.connectTimeoutMillis)
        assertEquals(300_000, http.writeTimeoutMillis)
        assertEquals(1_800_000, http.readTimeoutMillis)
    }

    @Test fun les_delais_valent_aussi_pour_le_client_epingle() {
        val http = Fabrique.client(ChargeAppairage("https://x:8787", "jeton", "a".repeat(64)))
        assertEquals(1_800_000, http.readTimeoutMillis)
    }
}
