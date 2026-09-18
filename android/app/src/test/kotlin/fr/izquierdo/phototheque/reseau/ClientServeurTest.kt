package fr.izquierdo.phototheque.reseau

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
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

    @Test fun le_plan_renvoie_session_et_empreintes() {
        serveur.enqueue(MockResponse().setBody(
            """{"session":"4bad0393fe5f4fd69635802c39699ce1","needed":["${"ab".repeat(32)}"]}"""))
        val r = client.plan(listOf(FichierPlan("DCIM/a.jpg", 954L, "ab".repeat(32))))
        assertEquals("4bad0393fe5f4fd69635802c39699ce1", r.session)
        assertEquals(1, r.needed.size)
    }

    @Test fun un_400_est_une_extension_refusee_pas_un_echec() {
        // Le contrat est formel : l'application doit POURSUIVRE la synchro.
        serveur.enqueue(MockResponse().setResponseCode(400).setBody(
            """{"detail":"extension non prise en charge : .webm"}"""))
        assertEquals(ResultatEnvoi.EXTENSION_REFUSEE,
            client.envoyer("s".repeat(32), "DCIM/a.webm", "x".byteInputStream(), 1L))
    }

    @Test fun un_401_signale_un_appareil_revoque() {
        serveur.enqueue(MockResponse().setResponseCode(401).setBody(
            """{"detail":"jeton invalide"}"""))
        assertEquals(ResultatEnvoi.REVOQUE,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L))
    }

    @Test fun un_500_est_un_echec_ordinaire() {
        serveur.enqueue(MockResponse().setResponseCode(500))
        assertEquals(ResultatEnvoi.ECHEC,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L))
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
