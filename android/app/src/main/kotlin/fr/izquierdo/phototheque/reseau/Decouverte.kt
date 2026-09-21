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
                        val hote = resolu.host?.hostAddress ?: return
                        // Une adresse IPv6 doit être entre crochets dans une
                        // URL, sinon la chaîne produite est invalide et le
                        // candidat est écarté EN SILENCE — l'application dirait
                        // « pas à la maison » alors que le serveur répond.
                        val adresse = if (hote.contains(':')) "[$hote]" else hote
                        synchronized(trouvees) {
                            trouvees += "https://$adresse:${resolu.port}"
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
        val empreinte = charge.certSha256
            ?: return OkHttpClient.Builder()          // serveur sans TLS
                .retryOnConnectionFailure(false)      // voir plus bas
                .build()
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
            // Le corps d'un envoi est adossé à un flux déjà consommé et fermé :
            // OkHttp ne doit JAMAIS rejouer une requête, sinon il enverrait du
            // vide sous la taille annoncée et le serveur rangerait un fichier
            // tronqué. Poser isOneShot() sur la partie fichier ne suffit pas —
            // OkHttp n'interroge que le corps de plus haut niveau, ici le
            // MultipartBody, qui hérite du défaut false.
            .retryOnConnectionFailure(false)
            .build()
    }

    /**
     * Cherche le serveur : d'abord les adresses annoncées en mDNS, puis l'url
     * du QR en secours. Renvoie null si rien ne répond — ce qui veut
     * simplement dire « pas à la maison », et n'est PAS une panne.
     *
     * Lève [ServeurRevoqueException] si un serveur a RÉPONDU et nous refuse :
     * c'est le seul cas qui doit remonter, parce que c'est le seul qui ne se
     * réglera pas tout seul.
     */
    fun serveur(context: Context, charge: ChargeAppairage): Serveur? {
        val http = client(charge)
        for (base in Decouverte.adresses(context) + charge.url) {
            val candidat = ClientServeur(base, charge.token, http)
            try {
                candidat.horizon()
                return Adaptateur(candidat)
            } catch (e: ServeurRevoqueException) {
                // Le serveur nous a RÉPONDU, et il nous refuse. Ce n'est pas
                // « introuvable » : inutile d'essayer les autres adresses, et
                // surtout il faut que l'appelant le sache.
                throw e
            } catch (e: Exception) {
                // Injoignable, certificat refusé, serveur en erreur : on essaie
                // l'adresse suivante. Ce chemin-là reste bien silencieux.
            }
        }
        return null
    }
}

/** Branche ClientServeur (réseau) sur l'interface attendue par l'orchestrateur. */
private class Adaptateur(private val c: ClientServeur) : Serveur {
    override fun horizon() = c.horizon()
    override fun plan(fichiers: List<FichierPlan>) = c.plan(fichiers)
    override fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long,
                         empreinteAttendue: String) =
        c.envoyer(session, chemin, flux, taille, empreinteAttendue)
    override fun commit(session: String, horizons: Map<String, Double>) =
        c.commit(session, horizons)
}
