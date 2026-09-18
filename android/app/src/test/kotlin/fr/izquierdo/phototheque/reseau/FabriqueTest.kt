package fr.izquierdo.phototheque.reseau

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
}
