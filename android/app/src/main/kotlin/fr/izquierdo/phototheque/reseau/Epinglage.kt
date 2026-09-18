package fr.izquierdo.phototheque.reseau

import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.X509TrustManager

/**
 * Vérification de l'identité du serveur par l'empreinte de son certificat.
 *
 * Le certificat du NUC est AUTO-SIGNÉ : aucune autorité ne le garantit, donc la
 * validation habituelle échoue toujours. L'épinglage ne s'ajoute pas à cette
 * validation, il la REMPLACE — c'est l'empreinte transmise dans le QR qui fait
 * foi. Une adresse IP change et un nom .local peut être usurpé sur un réseau
 * local ; l'empreinte du certificat, non.
 */
object Epinglage {

    /** SHA-256 du certificat au format DER, en hexadécimal minuscule. */
    fun empreinte(certificat: X509Certificate): String =
        MessageDigest.getInstance("SHA-256")
            .digest(certificat.encoded)
            .joinToString("") { "%02x".format(it) }
}

class GestionnaireEpingle(empreinteAttendue: String) : X509TrustManager {

    private val attendue = empreinteAttendue.lowercase()

    override fun checkServerTrusted(chain: Array<X509Certificate>?, authType: String?) {
        val presente = chain?.firstOrNull()
            ?: throw CertificateException("le serveur n'a presente aucun certificat")
        val obtenue = Epinglage.empreinte(presente)
        // Comparaison en temps constant, par principe : ce n'est pas un secret,
        // mais on ne prend pas l'habitude de comparer des empreintes autrement.
        if (!MessageDigest.isEqual(obtenue.toByteArray(), attendue.toByteArray())) {
            throw CertificateException(
                "certificat inattendu : $obtenue, attendu $attendue")
        }
    }

    /** L'application ne présente jamais de certificat client. */
    override fun checkClientTrusted(chain: Array<X509Certificate>?, authType: String?) =
        throw CertificateException("non utilise")

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}
