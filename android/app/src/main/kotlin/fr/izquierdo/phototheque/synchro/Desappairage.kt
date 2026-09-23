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
}
