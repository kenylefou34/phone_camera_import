package fr.izquierdo.phototheque.medias

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
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
}
