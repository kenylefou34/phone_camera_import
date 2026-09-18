package fr.izquierdo.phototheque.appairage

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AppairageTest {

    @Test fun un_qr_valide_est_lu() {
        val charge = Appairage.lire(
            """{"url":"https://IZQUIERDO-NUC.local:8787","token":"abc","cert_sha256":"${"0f".repeat(32)}"}""")
        assertEquals("abc", charge!!.token)
    }

    @Test fun un_qr_illisible_renvoie_null_sans_lever() {
        // L'utilisateur peut scanner n'importe quel code-barres : un plantage
        // de l'application serait la pire reponse possible.
        assertNull(Appairage.lire("ceci n'est pas du JSON"))
        assertNull(Appairage.lire(""))
        assertNull(Appairage.lire("""{"autre":"chose"}"""))
    }

    @Test fun un_qr_sans_empreinte_reste_valide() {
        // Serveur lance a la main en HTTP : accepte, mais sans epinglage.
        val charge = Appairage.lire("""{"url":"http://x:8787","token":"t","cert_sha256":null}""")
        assertNull(charge!!.certSha256)
    }
}
