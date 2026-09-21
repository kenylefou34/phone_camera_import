package fr.izquierdo.phototheque.medias

import java.io.InputStream
import java.security.MessageDigest

/**
 * Empreinte de contenu, lue par blocs.
 *
 * Jamais `readBytes()` : une vidéo de 3 Go tient rarement dans la mémoire
 * autorisée à une application Android, et le processus est tué sans explication.
 * Même raisonnement que côté serveur (issue #21).
 */
object Empreintes {

    const val TAILLE_BLOC = 1024 * 1024      // 1 Mio

    fun sha256(flux: InputStream): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val tampon = ByteArray(TAILLE_BLOC)
        flux.use {
            while (true) {
                val lus = it.read(tampon, 0, TAILLE_BLOC)
                if (lus < 0) break              // -1 = fin de flux, la seule vraie fin
                if (lus == 0) continue          // 0 transitoire : on redemande, on ne tronque pas
                digest.update(tampon, 0, lus)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
