package fr.izquierdo.phototheque.reseau

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import fr.izquierdo.phototheque.synchro.Serveur
import okhttp3.OkHttpClient
import java.io.InputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext

object Decouverte {

    private const val TYPE = "_phototheque._tcp."

    /** Adresses « https://hôte:port » annoncées sur le réseau local. */
    fun adresses(context: Context, delaiMs: Long = 3000): List<String> {
        val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
        val trouvees = mutableListOf<String>()
        val fini = CountDownLatch(1)

        val ecouteur = object : NsdManager.DiscoveryListener {
            override fun onServiceFound(info: NsdServiceInfo) {
                nsd.resolveService(info, object : NsdManager.ResolveListener {
                    override fun onServiceResolved(resolu: NsdServiceInfo) {
                        synchronized(trouvees) {
                            trouvees += "https://${resolu.host.hostAddress}:${resolu.port}"
                        }
                    }
                    override fun onResolveFailed(i: NsdServiceInfo, code: Int) = Unit
                })
            }
            override fun onDiscoveryStarted(type: String) = Unit
            override fun onServiceLost(info: NsdServiceInfo) = Unit
            override fun onDiscoveryStopped(type: String) { fini.countDown() }
            override fun onStartDiscoveryFailed(t: String, c: Int) { fini.countDown() }
            override fun onStopDiscoveryFailed(t: String, c: Int) { fini.countDown() }
        }

        nsd.discoverServices(TYPE, NsdManager.PROTOCOL_DNS_SD, ecouteur)
        fini.await(delaiMs, TimeUnit.MILLISECONDS)
        runCatching { nsd.stopServiceDiscovery(ecouteur) }
        return synchronized(trouvees) { trouvees.toList() }
    }
}

object Fabrique {

    /** Client HTTP qui n'accepte QUE le certificat annoncé dans le QR. */
    fun client(charge: ChargeAppairage): OkHttpClient {
        val empreinte = charge.certSha256 ?: return OkHttpClient()   // serveur sans TLS
        val gestionnaire = GestionnaireEpingle(empreinte)
        val contexte = SSLContext.getInstance("TLS").apply {
            init(null, arrayOf(gestionnaire), java.security.SecureRandom())
        }
        return OkHttpClient.Builder()
            .sslSocketFactory(contexte.socketFactory, gestionnaire)
            // Le certificat est auto-signé et son nom d'hôte peut ne pas
            // correspondre à l'adresse IP trouvée en mDNS. C'est l'empreinte
            // qui fait foi, pas le nom : voir docs/CONTRAT-APP.md section 3.
            .hostnameVerifier { _, _ -> true }
            .build()
    }

    /**
     * Cherche le serveur : d'abord les adresses annoncées en mDNS, puis l'url
     * du QR en secours. Renvoie null si rien ne répond — ce qui veut
     * simplement dire « pas à la maison », et n'est PAS une panne.
     */
    fun serveur(context: Context, charge: ChargeAppairage): Serveur? {
        val http = client(charge)
        for (base in Decouverte.adresses(context) + charge.url) {
            val candidat = ClientServeur(base, charge.token, http)
            val vivant = runCatching { candidat.horizon() }.isSuccess
            if (vivant) return Adaptateur(candidat)
        }
        return null
    }
}

/** Branche ClientServeur (réseau) sur l'interface attendue par l'orchestrateur. */
private class Adaptateur(private val c: ClientServeur) : Serveur {
    override fun horizon() = c.horizon()
    override fun plan(fichiers: List<FichierPlan>) = c.plan(fichiers)
    override fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long) =
        c.envoyer(session, chemin, flux, taille)
    override fun commit(session: String, horizons: Map<String, Double>) =
        c.commit(session, horizons)
}
