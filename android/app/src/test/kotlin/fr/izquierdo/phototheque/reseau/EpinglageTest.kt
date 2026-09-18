package fr.izquierdo.phototheque.reseau

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

class EpinglageTest {

    /** Certificat auto-signe engendre a l'etape 1, colle ici tel quel. Il n'a
     *  pas besoin d'etre secret : il ne sert qu'a verifier que l'epinglage
     *  accepte le bon certificat et refuse tous les autres. */
    private val certPem = """
        -----BEGIN CERTIFICATE-----
        MIIDEzCCAfugAwIBAgIUU6CHIm2nOAncyKzHvT9BUKCDrygwDQYJKoZIhvcNAQEL
        BQAwGTEXMBUGA1UEAwwOdGVzdC1lcGluZ2xhZ2UwHhcNMjYwOTE4MTcwNTU5WhcN
        MzYwOTE1MTcwNTU5WjAZMRcwFQYDVQQDDA50ZXN0LWVwaW5nbGFnZTCCASIwDQYJ
        KoZIhvcNAQEBBQADggEPADCCAQoCggEBAJ5FrxihKGXget1dEUZdwM4Fq7mPO3S1
        s9+ZJjOEzfUPntPkb2vt1KuVGd+OEY5FXSfUohwF2yLWWiaRYhHKS/jImDP0ZwNU
        XaJGmBa9Ns4r1f2yFeF3SKYoJWoaSZkuDnS1B9cCNiqArEe+/gyDKsIis2iAceE4
        2gizpkhiITWYQ5jpiev+hp0jsvgC3X9BfihvayV1TWA4KibmJ+Ng3GR+Sgwn4Xhj
        NdTYGX+swpuLZUxb21LQJhlE8XLWgnav2pAWTkogCvKnGSEJ5TkInf8W4d7eHKRg
        gnGwPn00yFqMHoP4e+UT0djZYFL4jhMKJaQz69YpLJqLP2YpWa1qKFECAwEAAaNT
        MFEwHQYDVR0OBBYEFHIWEMSXQM1X5yyY+jq6lx4EfQEdMB8GA1UdIwQYMBaAFHIW
        EMSXQM1X5yyY+jq6lx4EfQEdMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQEL
        BQADggEBAAKUC/M/5m+KWzQT5dVgjUpySFSILB3m5982Ht6TwORpcfX4HtITtV6v
        4TGrkRgrq1xR5edg5c9Z2/fp9+FpCiFHOUJIFIu/V5epkHazN6IzmJprwJ2YYFP7
        1nyhAAfolYQtkMV0cMIrWFtHR/5rQPnPZuRs7zZk0fCMq0xBh40kOVxiSrk1csUO
        nfsB0PkobEaqtXs6aaMFgEzCIsvEDj928s3p44gI17VIv/uLwpC+6t67lBmRXeMV
        Yd74Acq3whlZkKYkX6CS49503HbKHxtVjetfGXx70VnVU03N4aQUNj5kRrYUz9x3
        vO6+9uEPAnZjx1YbczaUb/uEprxGAfY=
        -----END CERTIFICATE-----
    """.trimIndent()

    private fun certificat(): X509Certificate =
        CertificateFactory.getInstance("X.509")
            .generateCertificate(certPem.byteInputStream()) as X509Certificate

    @Test fun l_empreinte_fait_64_caracteres_hexadecimaux_minuscules() {
        val e = Epinglage.empreinte(certificat())
        assertEquals(64, e.length)
        assertTrue("empreinte non hexadecimale : $e", e.all { it in "0123456789abcdef" })
    }

    @Test fun le_bon_certificat_est_accepte() {
        val attendue = Epinglage.empreinte(certificat())
        GestionnaireEpingle(attendue)
            .checkServerTrusted(arrayOf(certificat()), "RSA")   // ne doit rien lever
    }

    @Test fun un_certificat_inattendu_est_refuse() {
        try {
            GestionnaireEpingle("00".repeat(32))
                .checkServerTrusted(arrayOf(certificat()), "RSA")
            fail("un certificat inattendu a ete accepte")
        } catch (e: CertificateException) {
            // attendu
        }
    }

    @Test fun la_casse_de_l_empreinte_attendue_est_sans_importance() {
        val attendue = Epinglage.empreinte(certificat()).uppercase()
        GestionnaireEpingle(attendue).checkServerTrusted(arrayOf(certificat()), "RSA")
    }

    @Test fun une_chaine_vide_est_refusee() {
        // Le trou classique de ce genre de code : une chaine sans certificat ne
        // doit jamais etre traitee comme un cas passant. Sans ce test, un
        // refactor en `chain!!.first()` ne ferait rougir personne.
        try {
            GestionnaireEpingle("ab".repeat(32)).checkServerTrusted(emptyArray(), "RSA")
            fail("une chaine vide a ete acceptee")
        } catch (e: CertificateException) {
            // attendu
        }
    }

    @Test fun une_chaine_nulle_est_refusee() {
        try {
            GestionnaireEpingle("ab".repeat(32)).checkServerTrusted(null, "RSA")
            fail("une chaine nulle a ete acceptee")
        } catch (e: CertificateException) {
            // attendu
        }
    }
}
