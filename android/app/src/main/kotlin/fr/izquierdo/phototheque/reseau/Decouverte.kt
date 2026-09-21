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

    /**
     * Délais communs aux deux clients.
     *
     * OkHttp applique 10 s par défaut, y compris en lecture. Le 21/09/2026, le
     * `commit` d'une session de 971 fichiers et 14 Go a demandé 1 h 02 : le
     * téléphone a raccroché au bout de dix secondes, affiché « la sauvegarde a
     * échoué » et laissé le compteur sur « Jamais sauvegardé » — pendant que
     * le serveur rangeait tout parfaitement. Une réussite annoncée comme une
     * panne, le contraire exact de ce que la conception garantit.
     *
     * 30 min en lecture ne suffiraient PAS pour un commit monolithique : c'est
     * le découpage en paquets (`synchro.Paquets`) qui borne le travail d'un
     * commit, le délai ne fait que le protéger.
     *
     * Ce délai-là est réservé au commit et à l'envoi ; [clientCourt] en dérive
     * la version 30 s que réclame la spec §8 pour le reste.
     */
    private fun OkHttpClient.Builder.avecDelais(): OkHttpClient.Builder = this
        .connectTimeout(10, TimeUnit.SECONDS)
        // Une video de 3 Go a 12 Mo/s prend plusieurs minutes a ecrire.
        .writeTimeout(5, TimeUnit.MINUTES)
        .readTimeout(30, TimeUnit.MINUTES)

    /**
     * Le même client, mais qui n'attend une réponse que 30 s (spec §8).
     *
     * Appliquer les 30 min du commit à tout le reste est une régression
     * franche : un candidat mDNS périmé qui accepte la connexion TCP sans
     * jamais répondre bloquerait la découverte **30 min par adresse**, écran
     * vierge, avant la toute première publication d'avancement. Avant ce lot,
     * c'était 10 s.
     *
     * Dérivé par `newBuilder()` et non reconstruit : l'épinglage du
     * certificat, le vérificateur de nom d'hôte et l'interdiction de rejeu
     * sont conservés tels quels — et le pool de connexions est partagé.
     */
    fun clientCourt(long: OkHttpClient): OkHttpClient =
        long.newBuilder().readTimeout(30, TimeUnit.SECONDS).build()

    /** Client HTTP qui n'accepte QUE le certificat annoncé dans le QR. */
    fun client(charge: ChargeAppairage): OkHttpClient {
        val empreinte = charge.certSha256
            ?: return OkHttpClient.Builder()          // serveur sans TLS
                .retryOnConnectionFailure(false)      // voir plus bas
                .avecDelais()
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
            .avecDelais()
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
        // La sonde ci-dessous est un `horizon()`, donc elle passe par le
        // client court : une adresse morte est ecartee en 30 s, pas en 30 min.
        val court = clientCourt(http)
        for (base in Decouverte.adresses(context) + charge.url) {
            val candidat = ClientServeur(base, charge.token, http, court)
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
    override fun abandonner(session: String) = c.abandonner(session)
}
