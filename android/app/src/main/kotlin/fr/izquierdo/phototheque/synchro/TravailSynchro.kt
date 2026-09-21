package fr.izquierdo.phototheque.synchro

import android.content.Context
import androidx.work.*
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.reseau.Fabrique
import fr.izquierdo.phototheque.reseau.ServeurRevoqueException
import fr.izquierdo.phototheque.ui.Memoire
import fr.izquierdo.phototheque.ui.EtatSynchro
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

/**
 * Ce qu'une synchronisation laisse derriere elle, pour que l'ecran puisse le
 * dire. Publier le seul Bilan ne suffit pas : trois des cinq pannes sortent
 * AVANT qu'un bilan existe, et `dossiersVus` ne vit que dans l'avancement,
 * qui est remis a null en fin de course.
 */
data class IssueSynchro(
    val bilan: Bilan? = null,
    val serveurIntrouvable: Boolean = false,
    val erreur: String? = null,
    val revoque: Boolean = false,
    val dossiersVus: Map<String, Int> = emptyMap(),
)

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

        // CoroutineWorker s'execute par defaut sur Dispatchers.Default, dont
        // le pool est dimensionne au nombre de coeurs. Fabrique.serveur et
        // Orchestrateur.synchroniser sont BLOQUANTS et peuvent tenir un
        // thread une heure (ModeleAccueil avait deja fait ce choix
        // explicitement). `CoroutineWorker.coroutineContext` existe pour ca,
        // mais il est deprecie depuis work-runtime 2.9.0 au profit de
        // withContext(...) ici meme.
        val serveur = try {
            withContext(Dispatchers.IO) { Fabrique.serveur(contexte, charge) }
        } catch (e: ServeurRevoqueException) {
            Coffre(contexte).oublier()
            _avancement.value = null
            _derniereIssue.value = IssueSynchro(revoque = true)
            return Result.success()
        } ?: run {
            // Pas a la maison : ce n'est PAS une panne. On ne reessaie pas en
            // boucle : NetworkType.CONNECTED se contente d'un reseau
            // quelconque (la 4G y compris) et ne garantit pas qu'on soit a la
            // maison, donc rien ici ne redeclenchera au retour. C'est un
            // prochain lancement, manuel ou planifie, qui retentera.
            _avancement.value = null
            _derniereIssue.value = IssueSynchro(serveurIntrouvable = true)
            return Result.success()
        }

        // Retenu au fil des publications de l'orchestrateur : c'est la seule
        // source de `dossiersVus`, et sans cette variable la valeur serait
        // perdue des que `_avancement` repasse a null en fin de course.
        var dossiersVus = emptyMap<String, Int>()
        var dernierePhasePubliee: Phase? = null
        var dernierPourcentagePublie = -1

        val bilan = try {
            withContext(Dispatchers.IO) {
                Orchestrateur(
                    depot, serveur,
                    surAvancement = { vu ->
                        _avancement.value = vu
                        dossiersVus = vu.dossiersVus
                        // On ne republie la notification que si la phase ou
                        // le pourcentage entier a change : sans ce filtre,
                        // l'orchestrateur appelle ce callback jusqu'a deux
                        // fois par media, en rafales instantanees quand les
                        // fichiers sont deja connus du serveur - des
                        // milliers d'appels sur un gros lot.
                        if (vu.phase != dernierePhasePubliee ||
                            vu.pourcentage != dernierPourcentagePublie) {
                            dernierePhasePubliee = vu.phase
                            dernierPourcentagePublie = vu.pourcentage
                            setForegroundAsync(ServiceSynchro.information(contexte, vu))
                        }
                    },
                ).synchroniser(DOSSIERS_SAUVEGARDES, interrompu = { isStopped })
            }
        } catch (e: ServeurRevoqueException) {
            Coffre(contexte).oublier()
            _avancement.value = null
            _derniereIssue.value = IssueSynchro(revoque = true, dossiersVus = dossiersVus)
            return Result.success()
        } catch (e: Exception) {
            _avancement.value = null
            _derniereIssue.value = IssueSynchro(
                erreur = e.message ?: e.javaClass.simpleName, dossiersVus = dossiersVus)
            // Bornee : une SecurityException (permission retiree) ne se
            // reglera jamais toute seule, et sans plafond WorkManager
            // relancerait a l'infini (delai double jusqu'a 5 h), recalculant
            // toutes les empreintes a chaque tentative.
            return if (runAttemptCount < TENTATIVES_MAX) Result.retry() else Result.success()
        }

        // Le 401 sur /sync/upload ne leve pas ServeurRevoqueException : il
        // ressort ici comme Bilan.revoque. Sans ce nettoyage, un jeton mort
        // survivrait aux redemarrages et l'accueil s'ouvrirait dessus
        // indefiniment.
        if (bilan.revoque) Coffre(contexte).oublier()

        // Un arret DEMANDE par l'utilisateur n'est pas une reussite muette :
        // le compter comme telle eteindrait l'alerte des 7 jours - le seul
        // filet du projet contre les pannes muettes - pour une semaine sur
        // une synchro arretee au bout de deux fichiers.
        if (!bilan.interrompu && EtatSynchro.estUneReussite(bilan, depot.accesRefuse())) {
            Memoire(contexte).enregistrerReussite(System.currentTimeMillis())
        }
        _derniereIssue.value = IssueSynchro(
            bilan = bilan, revoque = bilan.revoque, dossiersVus = dossiersVus)
        _avancement.value = null
        return if (Reprise.fautIlRelancer(bilan) && runAttemptCount < TENTATIVES_MAX)
            Result.retry() else Result.success()
    }

    companion object {
        /** Lot 1 : dossiers en dur. L'écran de choix arrive au lot 2. */
        val DOSSIERS_SAUVEGARDES =
            setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp")

        private const val NOM = "synchro"

        /** Au-dela, on arrete de relancer : un media illisible ou une
         *  permission retiree ne se reglent jamais tout seuls, et sans ce
         *  plafond WorkManager boucle indefiniment (delai double jusqu'a
         *  5 h), recalculant les empreintes a chaque tentative. */
        private const val TENTATIVES_MAX = 5

        private val _avancement = MutableStateFlow<Avancement?>(null)
        /** null quand aucune synchronisation ne tourne. */
        val avancement = _avancement.asStateFlow()

        private val _derniereIssue = MutableStateFlow<IssueSynchro?>(null)
        val derniereIssue = _derniereIssue.asStateFlow()

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
