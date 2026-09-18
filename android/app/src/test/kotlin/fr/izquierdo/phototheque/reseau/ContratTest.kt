package fr.izquierdo.phototheque.reseau

import kotlinx.serialization.decodeFromString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Les charges utiles viennent de docs/CONTRAT-APP.md, capturees en vrai. */
class ContratTest {

    @Test fun charge_du_qr() {
        val brut = """
            {"url":"https://IZQUIERDO-NUC.local:8787",
             "token":"SLgiMxHinPOYVMZMEO_jEAYT9vQIbxkXMFfm5BgixTw",
             "cert_sha256":"02f00ed30b8e621f38681b89ae14dd69d4936b180a0bd88318344157cf3a05fb"}
        """.trimIndent()
        val charge = Contrat.json.decodeFromString<ChargeAppairage>(brut)
        assertEquals("https://IZQUIERDO-NUC.local:8787", charge.url)
        assertEquals(64, charge.certSha256!!.length)
    }

    @Test fun le_certificat_du_qr_peut_etre_absent() {
        // Serveur lance a la main en HTTP : pas d'epinglage possible.
        val charge = Contrat.json.decodeFromString<ChargeAppairage>(
            """{"url":"http://192.168.1.21:8787","token":"x","cert_sha256":null}""")
        assertNull(charge.certSha256)
    }

    @Test fun horizon_premiere_synchro() {
        val r = Contrat.json.decodeFromString<ReponseHorizon>(
            """{"depuis":"2026-09-01","dossiers":{}}""")
        assertEquals("2026-09-01", r.depuis)
        assertEquals(emptyMap<String, Double>(), r.dossiers)
    }

    @Test fun depuis_peut_valoir_null_ce_qui_signifie_aucune_limite() {
        val r = Contrat.json.decodeFromString<ReponseHorizon>(
            """{"depuis":null,"dossiers":{"DCIM/Camera":1789000000.0}}""")
        assertNull(r.depuis)
        assertEquals(1789000000.0, r.dossiers["DCIM/Camera"]!!, 0.001)
    }

    @Test fun reponse_du_plan_contient_des_empreintes_pas_des_chemins() {
        val r = Contrat.json.decodeFromString<ReponsePlan>(
            """{"session":"4bad0393fe5f4fd69635802c39699ce1",
                "needed":["c777d42e972fefb334f506835d77ad0ab12500b5a4db7fe29fe995faf8df80f7"]}""")
        assertEquals(32, r.session.length)
        assertEquals(64, r.needed.first().length)
    }

    @Test fun la_requete_du_plan_porte_les_trois_champs_obligatoires() {
        // path et size ne sont jamais lus par le serveur, mais les omettre
        // donne un 422 (verifie). Voir CONTRAT-APP.md section 4.2.
        val encode = Contrat.json.encodeToString(
            RequetePlan.serializer(),
            RequetePlan(listOf(FichierPlan("DCIM/a.jpg", 954L, "ab".repeat(32)))))
        assert(encode.contains("\"path\""))
        assert(encode.contains("\"size\""))
        assert(encode.contains("\"hash\""))
    }
}
