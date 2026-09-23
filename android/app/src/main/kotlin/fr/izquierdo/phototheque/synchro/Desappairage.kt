package fr.izquierdo.phototheque.synchro

/** Ce qu'a donné un désappairage. L'effacement local, lui, a toujours eu lieu. */
data class ResultatDesappairage(val serveurPrevenu: Boolean)

/**
 * Désappairage : couper le lien.
 *
 * Ce n'est PAS le moyen de tout reprendre — la date de début fait ce travail,
 * sans rescanner de QR et de façon réversible. Son vrai métier est de se
 * dépanner et de changer de serveur.
 *
 * Or à ce moment précis, le serveur est injoignable par définition : si le
 * certificat du NUC a changé, l'épinglage fait échouer le TLS **avant** le
 * HTTP. L'effacement local ne peut donc rien attendre de lui.
 */
object Desappairage {

    fun executer(
        prevenirServeur: () -> Boolean,
        effacerLocal: () -> Unit,
    ): ResultatDesappairage {
        // Au mieux, et jamais bloquant. `Throwable` et non `Exception` : une
        // erreur de chargement de classe réseau ne doit pas non plus empêcher
        // l'utilisateur de se débloquer.
        val prevenu = try { prevenirServeur() } catch (e: Throwable) { false }
        // Inconditionnel, et APRÈS : c'est lui qui débloque.
        effacerLocal()
        return ResultatDesappairage(prevenu)
    }

    /**
     * Ce qui arrivera VRAIMENT à la prochaine synchronisation après un
     * réappairage — pour que l'écran de confirmation ne promette pas
     * l'inverse de ce qui se passe.
     *
     * `Orchestrateur.synchroniser` fait primer `reglages.debutJour` sur
     * l'horizon d'appairage du serveur : « La date de début choisie sur le
     * téléphone prime sur la date de depuis d'appairage du serveur »
     * (`Orchestrateur.kt`). Et côté serveur, `Devices.pair()`
     * (`phototheque/devices.py`) pose cet horizon à la date DU JOUR à
     * CHAQUE appairage, jamais à l'historique complet. D'où les deux cas :
     * - aucune date de début posée → le nouvel appareil ne reprendra que ce
     *   qui date d'aujourd'hui ou après, pas l'historique ;
     * - une date de début posée → elle SURVIT au désappairage (les
     *   réglages ne sont pas liés à un serveur) et continue de commander ce
     *   qui sera repris, l'horizon du serveur ne comptant alors pour rien.
     */
    fun consequenceReappairage(debutJour: String?): String = if (debutJour != null)
        "Le nouvel appairage reprendra depuis le $debutJour, la date que " +
        "vous avez déjà configurée dans « Quand sauvegarder »."
    else
        "Le nouvel appairage repartira de la date du jour : vos médias " +
        "plus anciens ne seront pas repris automatiquement. Pour les " +
        "reprendre, posez une date de début dans « Quand sauvegarder » " +
        "après le réappairage."
}
