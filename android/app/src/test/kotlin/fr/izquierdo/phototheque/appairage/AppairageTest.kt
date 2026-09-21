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

    @Test fun un_qr_aux_types_incorrects_renvoie_null_sans_lever() {
        // JSON syntaxiquement valide, mais dont les champs n'ont pas le bon
        // type. Un code-barres quelconque peut produire a peu pres n'importe
        // quoi : la fonction doit rendre null, jamais lever.
        assertNull(Appairage.lire("""{"url":"https://x:8787","token":123}"""))
        assertNull(Appairage.lire("""{"url":{"x":1},"token":"t"}"""))
        assertNull(Appairage.lire("""{"url":"https://x:8787","token":"t","cert_sha256":123}"""))
    }

    @Test fun un_json_qui_n_est_pas_un_objet_renvoie_null() {
        assertNull(Appairage.lire("null"))
        assertNull(Appairage.lire("[]"))
        assertNull(Appairage.lire("12345"))
        assertNull(Appairage.lire("\"une chaine\""))
    }

    @Test fun un_champ_obligatoire_manquant_a_lui_seul_renvoie_null() {
        // Le test existant couvre les DEUX champs absents a la fois. Chacun
        // isolement doit aussi etre refuse : un appairage a moitie rempli
        // echouerait plus tard, a la premiere synchro, sous une forme
        // incomprehensible pour l'utilisateur.
        assertNull(Appairage.lire("""{"url":"https://x:8787"}"""))
        assertNull(Appairage.lire("""{"token":"un-jeton"}"""))
    }
}
