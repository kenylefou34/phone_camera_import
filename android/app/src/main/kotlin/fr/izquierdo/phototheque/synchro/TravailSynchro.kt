package fr.izquierdo.phototheque.synchro

import android.content.Context
import androidx.work.*
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.reseau.Fabrique
import fr.izquierdo.phototheque.reseau.ServeurRevoqueException
import fr.izquierdo.phototheque.ui.Memoire
import fr.izquierdo.phototheque.ui.EtatSynchro
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * La synchronisation, exécutée par Android et non par l'écran.
 *
 * `WorkManager` garantit trois choses que le `viewModelScope` ne donnait pas :
 * le travail survit à la fermeture de l'application, il n'est lancé que
 * lorsqu'un réseau est disponible, et il est relancé tout seul après une
 * coupure subie.
 */
class TravailSynchro(
    context: Context,
    parametres: WorkerParameters,
) : CoroutineWorker(context, parametres) {

    override suspend fun doWork(): Result {
        val contexte = applicationContext
        val charge = Coffre(contexte).charge() ?: return Result.success()
        val depot = Depot(contexte)

        setForeground(ServiceSynchro.information(contexte, Avancement()))

        val serveur = try {
            Fabrique.serveur(contexte, charge)
        } catch (e: ServeurRevoqueException) {
            Coffre(contexte).oublier()
            _avancement.value = null
            return Result.success()
        } ?: run {
            // Pas a la maison : ce n'est PAS une panne. On ne reessaie pas en
            // boucle, la contrainte reseau de WorkManager s'en charge.
            _avancement.value = null
            return Result.success()
        }

        val bilan = try {
            Orchestrateur(
                depot, serveur,
                surAvancement = { vu ->
                    _avancement.value = vu
                    setForegroundAsync(ServiceSynchro.information(contexte, vu))
                },
            ).synchroniser(DOSSIERS_SAUVEGARDES, interrompu = { isStopped })
        } catch (e: ServeurRevoqueException) {
            Coffre(contexte).oublier()
            _avancement.value = null
            return Result.success()
        } catch (e: Exception) {
            _avancement.value = null
            return Result.retry()
        }

        if (EtatSynchro.estUneReussite(bilan, depot.accesRefuse())) {
            Memoire(contexte).enregistrerReussite(System.currentTimeMillis())
        }
        _dernierBilan.value = bilan
        _avancement.value = null
        return if (Reprise.fautIlRelancer(bilan)) Result.retry() else Result.success()
    }

    companion object {
        /** Lot 1 : dossiers en dur. L'écran de choix arrive au lot 2. */
        val DOSSIERS_SAUVEGARDES =
            setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp")

        private const val NOM = "synchro"

        private val _avancement = MutableStateFlow<Avancement?>(null)
        /** null quand aucune synchronisation ne tourne. */
        val avancement = _avancement.asStateFlow()

        private val _dernierBilan = MutableStateFlow<Bilan?>(null)
        val dernierBilan = _dernierBilan.asStateFlow()

        fun lancer(context: Context) {
            val demande = OneTimeWorkRequestBuilder<TravailSynchro>()
                .setConstraints(Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL,
                                    WorkRequest.MIN_BACKOFF_MILLIS,
                                    java.util.concurrent.TimeUnit.MILLISECONDS)
                .build()
            // KEEP et non REPLACE : deux appuis sur le bouton ne doivent pas
            // faire tourner deux synchros en parallele sur la meme
            // bibliotheque.
            WorkManager.getInstance(context)
                .enqueueUniqueWork(NOM, ExistingWorkPolicy.KEEP, demande)
        }

        fun interrompre(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(NOM)
        }
    }
}
