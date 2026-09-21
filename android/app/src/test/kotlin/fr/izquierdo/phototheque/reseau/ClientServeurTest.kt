package fr.izquierdo.phototheque.reseau

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/** Reponses issues de docs/CONTRAT-APP.md, capturees sur un echange reel. */
class ClientServeurTest {

    private lateinit var serveur: MockWebServer
    private lateinit var client: ClientServeur

    @Before fun demarrer() {
        serveur = MockWebServer().also { it.start() }
        client = ClientServeur(serveur.url("/").toString().trimEnd('/'),
                               "jeton-de-test", OkHttpClient())
    }

    @After fun arreter() = serveur.shutdown()

    /** Empreinte du contenu envoye, telle que l'application l'a calculee. */
    private val EMPREINTE = "c7".repeat(32)

    @Test fun le_jeton_est_envoye_en_bearer() {
        serveur.enqueue(MockResponse().setBody("""{"depuis":null,"dossiers":{}}"""))
        client.horizon()
        assertEquals("Bearer jeton-de-test",
            serveur.takeRequest().getHeader("Authorization"))
    }

    @Test fun horizon_est_lu() {
        serveur.enqueue(MockResponse().setBody(
            """{"depuis":"2026-09-01","dossiers":{"DCIM/Camera":1789000000.0}}"""))
        val r = client.horizon()
        assertEquals("2026-09-01", r.depuis)
        assertEquals(1789000000.0, r.dossiers["DCIM/Camera"]!!, 0.001)
    }

    @Test fun horizon_sur_un_401_leve_une_revocation_DISTINCTE() {
        // Le piege que ce test verrouille : sans lecture du code, le corps
        // {"detail":"jeton invalide"} fait echouer la deserialisation, et
        // l'exception obtenue est la MEME que celle d'un serveur injoignable.
        // L'appareil revoque afficherait alors « serveur introuvable » pour
        // toujours, sans jamais proposer de rescanner un QR.
        serveur.enqueue(MockResponse().setResponseCode(401).setBody(
            """{"detail":"jeton invalide"}"""))
        try {
            client.horizon()
            fail("un 401 sur /sync/horizon doit lever une revocation")
        } catch (e: ServeurRevoqueException) {
            // attendu
        }
    }

    @Test fun horizon_sur_un_500_leve_une_erreur_ordinaire_pas_une_revocation() {
        // Une panne serveur est VISIBLE mais reparable : la confondre avec une
        // revocation effacerait l'appairage pour rien.
        serveur.enqueue(MockResponse().setResponseCode(500))
        try {
            client.horizon()
            fail("un 500 sur /sync/horizon doit lever")
        } catch (e: ServeurRevoqueException) {
            fail("un 500 n'est pas une revocation")
        } catch (e: java.io.IOException) {
            assertTrue("le code doit figurer dans le message",
                e.message!!.contains("500"))
        }
    }

    @Test fun le_plan_sur_un_401_leve_aussi_une_revocation() {
        serveur.enqueue(MockResponse().setResponseCode(401).setBody(
            """{"detail":"jeton invalide"}"""))
        try {
            client.plan(listOf(FichierPlan("DCIM/a.jpg", 954L, "ab".repeat(32))))
            fail("un 401 sur /sync/plan doit lever une revocation")
        } catch (e: ServeurRevoqueException) {
            // attendu
        }
    }

    @Test fun le_plan_renvoie_session_et_empreintes() {
        serveur.enqueue(MockResponse().setBody(
            """{"session":"4bad0393fe5f4fd69635802c39699ce1","needed":["${"ab".repeat(32)}"]}"""))
        val r = client.plan(listOf(FichierPlan("DCIM/a.jpg", 954L, "ab".repeat(32))))
        assertEquals("4bad0393fe5f4fd69635802c39699ce1", r.session)
        assertEquals(1, r.needed.size)
    }

    @Test fun un_envoi_confirme_par_la_MEME_empreinte_est_un_succes() {
        serveur.enqueue(MockResponse().setBody("""{"ok":true,"hash":"$EMPREINTE"}"""))
        assertEquals(ResultatEnvoi.OK,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L, EMPREINTE))
    }

    @Test fun une_empreinte_renvoyee_DIFFERENTE_est_un_echec() {
        // Le contrat renvoie l'empreinte du fichier TEL QUE RECU. Une
        // difference signale un transfert abime : l'accepter ferait avancer
        // l'horizon par-dessus l'original sain, et la bibliotheque garderait la
        // copie corrompue sans que rien ne le signale jamais.
        serveur.enqueue(MockResponse().setBody(
            """{"ok":true,"hash":"${"ff".repeat(32)}"}"""))
        assertEquals(ResultatEnvoi.ECHEC,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L, EMPREINTE))
    }

    @Test fun une_coupure_reseau_en_plein_envoi_est_un_echec() {
        // Le seul rempart contre un envoi coupe. Sans lui, l'exception
        // remonterait jusqu'a l'orchestrateur, le commit n'aurait jamais lieu
        // et les fichiers deja recus resteraient bloques sur le NUC.
        serveur.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
        assertEquals(ResultatEnvoi.ECHEC,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L, EMPREINTE))
    }

    @Test fun le_commit_sur_une_reponse_non_200_leve() {
        // Sur 401/404/500 le corps s'analysait sans lever et donnait une map
        // vide : l'application croyait avoir reussi alors que AUCUN horizon
        // n'avait ete enregistre.
        serveur.enqueue(MockResponse().setResponseCode(500))
        try {
            client.commit("s".repeat(32), mapOf("DCIM/Camera" to 1789000000.0))
            fail("un commit refuse ne doit pas passer pour une reussite")
        } catch (e: java.io.IOException) {
            assertTrue(e.message!!.contains("500"))
        }
    }

    @Test fun le_commit_sur_un_401_leve_une_revocation() {
        serveur.enqueue(MockResponse().setResponseCode(401).setBody(
            """{"detail":"jeton invalide"}"""))
        try {
            client.commit("s".repeat(32), emptyMap())
            fail("un 401 sur /sync/commit doit lever une revocation")
        } catch (e: ServeurRevoqueException) {
            // attendu
        }
    }

    @Test fun un_400_est_une_extension_refusee_pas_un_echec() {
        // Le contrat est formel : l'application doit POURSUIVRE la synchro.
        serveur.enqueue(MockResponse().setResponseCode(400).setBody(
            """{"detail":"extension non prise en charge : .webm"}"""))
        assertEquals(ResultatEnvoi.EXTENSION_REFUSEE,
            client.envoyer("s".repeat(32), "DCIM/a.webm", "x".byteInputStream(), 1L, EMPREINTE))
    }

    @Test fun un_400_qui_ne_parle_PAS_d_extension_est_un_echec() {
        // Le serveur renvoie aussi 400 sur un chemin refuse (un chemin
        // commencant par « / », par exemple). EXTENSION_REFUSEE est la seule
        // issue qui fait AVANCER l'horizon sur un media non transfere : la
        // confondre avec ce cas-la ferait sauter l'horizon par-dessus un media
        // qui n'est jamais arrive, et il serait perdu pour toujours.
        serveur.enqueue(MockResponse().setResponseCode(400).setBody(
            """{"detail":"chemin refuse"}"""))
        assertEquals(ResultatEnvoi.ECHEC,
            client.envoyer("s".repeat(32), "/a.jpg", "x".byteInputStream(), 1L, EMPREINTE))
    }

    @Test fun un_401_signale_un_appareil_revoque() {
        serveur.enqueue(MockResponse().setResponseCode(401).setBody(
            """{"detail":"jeton invalide"}"""))
        assertEquals(ResultatEnvoi.REVOQUE,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L, EMPREINTE))
    }

    @Test fun un_500_est_un_echec_ordinaire() {
        serveur.enqueue(MockResponse().setResponseCode(500))
        assertEquals(ResultatEnvoi.ECHEC,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L, EMPREINTE))
    }

    @Test fun le_commit_transmet_les_horizons() {
        serveur.enqueue(MockResponse().setBody("""{"sorted":1,"errors":0}"""))
        client.commit("s".repeat(32), mapOf("DCIM/Camera" to 1789000000.0))

        // On analyse le JSON et on compare la VALEUR, pas sa representation.
        // Kotlin serialise 1789000000.0 en « 1.789E9 » : c'est du JSON valide,
        // et le vrai serveur le relit bien comme 1789000000.0 (verifie). Chercher
        // la chaine « 1789000000 » dans le corps testerait un detail de
        // formatage au lieu du contrat, et c'est ce que faisait le test d'avant.
        val corps = Json.parseToJsonElement(serveur.takeRequest().body.readUtf8()).jsonObject
        assertEquals("s".repeat(32), corps["session"]!!.jsonPrimitive.content)
        assertEquals(
            1789000000.0,
            corps["horizons"]!!.jsonObject["DCIM/Camera"]!!.jsonPrimitive.double,
            0.001)
    }
}
