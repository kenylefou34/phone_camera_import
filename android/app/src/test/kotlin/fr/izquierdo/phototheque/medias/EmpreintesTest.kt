package fr.izquierdo.phototheque.medias

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.assertFalse
import org.junit.Test
import java.io.InputStream

class EmpreintesTest {

    @Test fun empreinte_connue() {
        // sha256("") et sha256("abc"), valeurs de reference universelles.
        assertEquals("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            Empreintes.sha256("".byteInputStream()))
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            Empreintes.sha256("abc".byteInputStream()))
    }

    @Test fun le_fichier_n_est_jamais_lu_entierement_d_un_coup() {
        // Meme propriete que cote serveur (issue #21) : un flux qui refuse la
        // lecture integrale. Sur un telephone, avaler une video de 3 Go tue
        // l'application aussi surement que le service du NUC.
        val contenu = ByteArray(3 * 1024 * 1024) { (it % 251).toByte() }
        var plusGrandeDemande = 0
        val flux = object : InputStream() {
            private var position = 0
            override fun read(): Int = throw AssertionError("lecture octet par octet")
            override fun read(b: ByteArray, off: Int, len: Int): Int {
                if (len > Empreintes.TAILLE_BLOC)
                    throw AssertionError("bloc de $len octets demande, trop gros")
                plusGrandeDemande = maxOf(plusGrandeDemande, len)
                if (position >= contenu.size) return -1
                val n = minOf(len, contenu.size - position)
                contenu.copyInto(b, off, position, position + n)
                position += n
                return n
            }
        }
        Empreintes.sha256(flux)
        assertTrue(plusGrandeDemande in 1..Empreintes.TAILLE_BLOC)
    }

    @Test fun l_implementation_n_accumule_jamais_le_fichier_en_memoire() {
        // Le test precedent ne suffit PAS a l'interdire : readBytes() de la
        // bibliotheque standard lit par blocs de 8192 octets — sous le seuil
        // d'un Mio — tout en accumulant la totalite du fichier en memoire. Il
        // passerait donc les deux autres tests tout en provoquant exactement la
        // panne que ce module existe pour eviter (verifie en desassemblant le
        // bytecode de kotlin-stdlib).
        //
        // Un test unitaire ne peut pas observer la memoire accumulee par une
        // autre fonction. Il peut en revanche verrouiller l'API interdite.
        val source = java.io.File(
            "src/main/kotlin/fr/izquierdo/phototheque/medias/Empreintes.kt").readText()
        // Supprimer les commentaires (simples et blocs)
        var codeSeul = source.replace(Regex("""/\*[\s\S]*?\*/"""), "")  // /* ... */
        codeSeul = codeSeul.split("\n")
            .filterNot { it.trimStart().startsWith("//") }
            .joinToString("\n")
        assertFalse(
            "Empreintes.kt ne doit jamais accumuler le fichier en memoire",
            codeSeul.contains("readBytes(") || codeSeul.contains(".bytes()"))
    }
}
