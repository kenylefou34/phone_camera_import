package fr.izquierdo.phototheque.reseau

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
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

        // Le client court est DERIVE du precedent : s'il etait reconstruit,
        // il perdrait ce drapeau -- et c'est lui qui sonde le reseau.
        assertFalse("client court", Fabrique.clientCourt(avecTls).retryOnConnectionFailure)
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

    @Test fun la_sonde_de_decouverte_n_attend_pas_trente_minutes() {
        // Spec 8 : 30 s pour horizon/plan, 30 min pour le seul commit.
        // Appliquer les 30 min partout est une regression franche : un
        // candidat mDNS perime qui accepte la connexion TCP sans jamais
        // repondre bloquerait la decouverte 30 min PAR ADRESSE, ecran vierge,
        // avant la premiere publication d'avancement. Avant ce lot : 10 s.
        val long = Fabrique.client(ChargeAppairage("https://x:8787", "jeton", "a".repeat(64)))
        val court = Fabrique.clientCourt(long)
        assertEquals(30_000, court.readTimeoutMillis)
        // Le commit, lui, garde ses 30 min : deriver le court ne doit pas
        // avoir abime le long.
        assertEquals(1_800_000, long.readTimeoutMillis)
        // Et le court garde le reste des reglages, epinglage compris : le
        // reconstruire au lieu de le deriver ouvrirait la connexion de sonde
        // a n'importe quel certificat.
        assertEquals(10_000, court.connectTimeoutMillis)
        assertEquals(300_000, court.writeTimeoutMillis)
        assertSame(long.sslSocketFactory, court.sslSocketFactory)
        assertSame(long.hostnameVerifier, court.hostnameVerifier)
    }
}
