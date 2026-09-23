package fr.izquierdo.phototheque.synchro

import android.content.Context
import androidx.work.*
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.reseau.Fabrique
import fr.izquierdo.phototheque.reseau.ServeurRevoqueException
import fr.izquierdo.phototheque.ui.MagasinReglages
import fr.izquierdo.phototheque.ui.Memoire
import fr.izquierdo.phototheque.ui.EtatSynchro
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
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
    // null = aucun avancement n'a jamais ete publie (panne avant la premiere
    // lecture de MediaStore). Une carte VIDE est une vraie reponse — le cas
    // le plus grave, cf EtatSynchro.dossiersVus — et ne doit jamais etre
    // confondue avec l'absence de reponse.
    val dossiersVus: Map<String, Int>? = null,
    // Vide par défaut : seule la fin RÉUSSIE de doWork() le calcule. Les
    // sorties en panne (révocation, annulation, exception) n'ont rien de
    // fiable à dire ici - autant ne rien annoncer que d'annoncer à tort.
    val dossiersNouveaux: Set<String> = emptySet(),
)

/**
 * Ce que WorkManager sait du travail de synchronisation.
 *
 * Les trois états actifs sont séparés parce que l'écran doit en dire trois
 * choses différentes, et qu'une seule phrase pour tous serait fausse deux fois
 * sur trois :
 * - EN_ATTENTE : rien ne tourne, la contrainte réseau n'est pas satisfaite ;
 * - NOUVELLE_TENTATIVE : rien ne tourne non plus, mais une exécution a DÉJÀ eu
 *   lieu et a demandé à être reprise. Dire « en attente d'un réseau » ici
 *   serait faux — le cas le plus fréquent est une permission retirée, dont le
 *   bandeau dit déjà, et correctement, qu'il faut aller dans les réglages ;
 * - EN_COURS : le travail s'exécute, mais tant qu'il n'a rien publié l'accueil
 *   reste le seul écran visible.
 */
enum class EtatTravail { INACTIF, EN_ATTENTE, NOUVELLE_TENTATIVE, EN_COURS }

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
        // `_derniereIssue` est un StateFlow de companion object, donc de la
        // duree de vie du processus : sans cette remise a zero, un nouveau
        // collecteur (ecran recree, nouvelle synchro) rejouerait l'issue de
        // l'execution PRECEDENTE - un vieux bandeau d'erreur qui reapparait.
        _derniereIssue.value = null
        // Une execution neuve n'a recu aucun ordre d'arret. Sans cette remise
        // a zero, un arret demande lors de la synchro PRECEDENTE ferait
        // annoncer « interrompue » a celle-ci.
        arretDemande = false
        val contexte = applicationContext

        // Retenu au fil des publications de l'orchestrateur : c'est la seule
        // source de `dossiersVus`, et sans cette variable la valeur serait
        // perdue des que `_avancement` repasse a null en fin de course.
        // Part de `null` (jamais publie), pas d'une carte vide : sinon une
        // panne survenue AVANT la premiere publication se lirait comme un
        // « MediaStore n'a rien rendu » qu'elle n'a jamais constate.
        var dossiersVus: Map<String, Int>? = null
        // Le bilan REEL, retenu au vol : une annulation empeche `withContext`
        // de le rendre (voir le catch de CancellationException), et sans lui
        // l'ecran annoncerait « 0 envoyes » apres vingt paquets valides.
        var bilanPartiel: Bilan? = null

        // Tout le corps est sous `try` : la preparation aussi. `setForeground`
        // leve sur Android 12+ quand le demarrage d'un service de premier plan
        // depuis l'arriere-plan est restreint - exactement le cas d'une
        // reprise automatique, application fermee. Hors du try, l'exception
        // marquait le travail en echec sans qu'aucun message n'existe nulle
        // part : ni avancement, ni bilan, ni erreur. La panne muette que tout
        // le sous-projet interdit.
        try {
            val charge = Coffre(contexte).charge() ?: return Result.success()
            val depot = Depot(contexte)
            val reglages = MagasinReglages(contexte).lire()

            setForeground(ServiceSynchro.information(contexte, Avancement()))

            // CoroutineWorker s'execute par defaut sur Dispatchers.Default,
            // dont le pool est dimensionne au nombre de coeurs. Fabrique.serveur
            // et Orchestrateur.synchroniser sont BLOQUANTS et peuvent tenir un
            // thread une heure (ModeleAccueil avait deja fait ce choix
            // explicitement). `CoroutineWorker.coroutineContext` existe pour
            // ca, mais il est deprecie depuis work-runtime 2.9.0 au profit de
            // withContext(...) ici meme.
            val serveur = withContext(Dispatchers.IO) { Fabrique.serveur(contexte, charge) }
                ?: run {
                    // Pas a la maison : ce n'est PAS une panne. On ne reessaie
                    // pas en boucle : NetworkType.CONNECTED se contente d'un
                    // reseau quelconque (la 4G y compris) et ne garantit pas
                    // qu'on soit a la maison, donc rien ici ne redeclenchera au
                    // retour. C'est un prochain lancement, manuel ou planifie,
                    // qui retentera.
                    _derniereIssue.value = IssueSynchro(serveurIntrouvable = true)
                    return Result.success()
                }

            var dernierePhasePubliee: Phase? = null
            // 0L : garantit la premiere publication de l'orchestrateur, quelle
            // que soit l'heure du telephone.
            var dernierePublicationMs = 0L

            val bilan = withContext(Dispatchers.IO) {
                Orchestrateur(
                    depot, serveur,
                    surAvancement = { vu ->
                        _avancement.value = vu
                        dossiersVus = vu.dossiersVus
                        // Republie si la phase change (toujours, immediat),
                        // ou si au moins une seconde s'est ecoulee depuis la
                        // derniere notification postee. Un filtre sur le
                        // pourcentage ENTIER ne suffit pas : sur une serie de
                        // petites photos, 1 % peut valoir des dizaines de
                        // fichiers, et le titre resterait fige plusieurs
                        // minutes sur l'unique surface visible ecran eteint.
                        // Et compter les fichiers plutot que le temps
                        // restaurerait la rafale d'origine (jusqu'a deux
                        // appels par media) des que le serveur connait deja
                        // tout, sans aucune E/S entre deux iterations.
                        val maintenant = System.currentTimeMillis()
                        if (vu.phase != dernierePhasePubliee ||
                            maintenant - dernierePublicationMs >= 1000) {
                            dernierePhasePubliee = vu.phase
                            dernierePublicationMs = maintenant
                            setForegroundAsync(ServiceSynchro.information(contexte, vu))
                        }
                    },
                ).synchroniser(reglages, interrompu = { isStopped })
                 // DANS le bloc, donc execute avant que `withContext` ne
                 // relaie l'annulation : c'est la seule facon de garder le
                 // travail deja accompli quand la synchro est coupee.
                 .also { bilanPartiel = it }
            }

            // Le 401 sur /sync/upload ne leve pas ServeurRevoqueException : il
            // ressort ici comme Bilan.revoque. Sans ce nettoyage, un jeton mort
            // survivrait aux redemarrages et l'accueil s'ouvrirait dessus
            // indefiniment.
            if (bilan.revoque) Coffre(contexte).oublier()

            // Un arret, demande ou subi, n'est pas une reussite muette : le
            // compter comme telle eteindrait l'alerte des 7 jours - le seul
            // filet du projet contre les pannes muettes - pour une semaine sur
            // une synchro arretee au bout de deux fichiers. Cette regle-la lit
            // le bilan BRUT : peu importe QUI a arrete, la synchro n'est pas
            // allee au bout.
            if (!bilan.interrompu && EtatSynchro.estUneReussite(bilan, depot.accesRefuse())) {
                Memoire(contexte).enregistrerReussite(System.currentTimeMillis())
            }

            // Les dossiers entrés par une coche récursive depuis la dernière
            // synchronisation. Une seule lecture, un seul `copy`, une seule
            // écriture : la tâche 7 ajoute une autre mise à jour au même
            // endroit (`debutApplique`), et deux `ecrire()` bâtis chacun sur
            // sa propre lecture s'écraseraient l'un l'autre selon l'ordre.
            val vus = dossiersVus?.keys.orEmpty()
            val magasin = MagasinReglages(contexte)
            val avant = magasin.lire()
            // Vide au tout premier lancement (aucune synchronisation
            // n'a encore rempli `dossiersConnus`) : sans cette garde, cette
            // toute première synchronisation annoncerait TOUS les dossiers
            // pris par une coche récursive comme « nouveaux », alors
            // qu'aucun ne l'est réellement - il n'y a simplement encore rien
            // eu à comparer. On se contente alors de remplir `dossiersConnus`.
            val nouveaux = if (avant.dossiersConnus.isEmpty()) emptySet()
                           else Choix.nouveauxParRecursivite(
                               vus, avant.dossiersConnus, avant.dossiersRecursifs)
            // `dossiersConnus` est rangé DANS LE MÊME geste que sa lecture :
            // sans cela, les mêmes dossiers seraient annoncés « nouveaux » à
            // chaque synchronisation, et l'avertissement deviendrait un bruit
            // qu'on apprend à ignorer.
            magasin.ecrire(avant.copy(dossiersConnus = vus))

            _derniereIssue.value = IssueSynchro(
                bilan = bilan.pourLEcran(), revoque = bilan.revoque, dossiersVus = dossiersVus,
                dossiersNouveaux = nouveaux)
            return if (Reprise.fautIlRelancer(bilan) && runAttemptCount < TENTATIVES_MAX)
                Result.retry() else Result.success()

        } catch (e: ServeurRevoqueException) {
            Coffre(contexte).oublier()
            _derniereIssue.value = IssueSynchro(revoque = true, dossiersVus = dossiersVus)
            return Result.success()
        } catch (e: CancellationException) {
            // Un arret, pas une panne. `cancelUniqueWork` annule le job du
            // worker ; `withContext` NE rend PAS la valeur de retour de
            // l'orchestrateur dans ce cas - il relaie l'annulation, et
            // CancellationException herite d'Exception sur la JVM. Sans ce
            // catch dedie AVANT le generique, celui-ci afficherait
            // « La sauvegarde a echoue : Job was cancelled ».
            _derniereIssue.value = IssueSynchro(
                // `bilanPartiel` et non des zeros : on peut arreter apres
                // vingt paquets valides et six cents fichiers montes.
                // `interrompu = true` sur le repli, et ce n'est pas
                // decoratif : `pourLEcran()` ne sait que RETIRER ce drapeau.
                // Sans lui, un arret DEMANDE avant que l'orchestrateur ait
                // rendu quoi que ce soit - pendant les 3 a 13 s de
                // decouverte, ou pendant setForeground - afficherait
                // « 0 envoyes · 0 refuses · 0 en echec » sans un mot
                // d'explication. Ce chemin est facile a atteindre depuis que
                // l'accueil offre « Interrompre » pendant la decouverte.
                bilan = (bilanPartiel ?: Bilan(0, 0, 0, revoque = false,
                                               bilanServeur = emptyMap(),
                                               interrompu = true)).pourLEcran(),
                dossiersVus = dossiersVus,
            )
            throw e          // une annulation se relance TOUJOURS
        } catch (e: Exception) {
            _derniereIssue.value = IssueSynchro(
                erreur = e.message ?: e.javaClass.simpleName, dossiersVus = dossiersVus)
            // Bornee : une SecurityException (permission retiree) ne se
            // reglera jamais toute seule, et sans plafond WorkManager
            // relancerait a l'infini (delai double jusqu'a 5 h), recalculant
            // toutes les empreintes a chaque tentative.
            return if (runAttemptCount < TENTATIVES_MAX) Result.retry() else Result.success()
        } finally {
            // Un seul endroit, et il couvre TOUTES les sorties : il n'existe
            // plus d'etat dont l'ecran d'avancement ne sorte jamais. Ne touche
            // qu'a `_avancement`, pour ne pas ecraser l'issue qu'une branche
            // vient de publier.
            _avancement.value = null
        }
    }

    /**
     * Le bilan tel que l'ECRAN doit l'annoncer.
     *
     * « Sauvegarde interrompue. » est une phrase sur une DECISION de
     * l'utilisateur. Or `isStopped` vaut aussi vrai pour une contrainte reseau
     * perdue ou un arret systeme : l'annoncer ainsi serait faux, et c'est
     * precisement ce que fait l'etape 7 de la recette (couper le Wi-Fi).
     * Les regles internes - reussite, reprise - continuent de lire le bilan
     * BRUT, pour lequel seul compte le fait que la synchro n'est pas allee au
     * bout.
     */
    private fun Bilan.pourLEcran(): Bilan = copy(interrompu = interrompu && arretDemande)

    companion object {
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

        /** Vrai quand l'arret vient de l'UTILISATEUR. `isStopped` ne suffit
         *  pas : il vaut aussi vrai pour une contrainte reseau perdue ou un
         *  arret systeme. @Volatile parce qu'il est ecrit depuis le fil de
         *  l'interface et lu depuis un fil d'E/S. */
        @Volatile private var arretDemande = false

        fun interrompre(context: Context) {
            // Pose AVANT l'annulation : c'est ce drapeau, et non `isStopped`,
            // qui distingue un arret demande d'une coupure subie.
            arretDemande = true
            WorkManager.getInstance(context).cancelUniqueWork(NOM)
        }

        /** Etat du travail, derive de WorkManager et non d'un drapeau pose a
         *  la main : un travail differe par la contrainte reseau resterait
         *  sinon « en cours » pour toujours, et l'utilisateur n'aurait aucun
         *  retour de son appui. Voir EtatTravail pour la raison des trois
         *  etats actifs.
         *
         *  `runAttemptCount` vaut 0 tant qu'aucune execution n'a eu lieu :
         *  c'est le seul signal qui separe « jamais demarre, on attend la
         *  contrainte » de « deja tente, on attend le delai de reprise ». Si
         *  WorkManager l'incrementait aussi en replanifiant apres une
         *  contrainte perdue, le pire serait d'annoncer une nouvelle
         *  tentative, ce qui reste VRAI — aucune des deux phrases ne peut
         *  devenir fausse. */
        fun etatTravail(context: Context): Flow<EtatTravail> =
            WorkManager.getInstance(context).getWorkInfosForUniqueWorkFlow(NOM)
                .map { infos ->
                    when {
                        infos.any { it.state == WorkInfo.State.RUNNING } ->
                            EtatTravail.EN_COURS
                        infos.any { !it.state.isFinished && it.runAttemptCount > 0 } ->
                            EtatTravail.NOUVELLE_TENTATIVE
                        infos.any { !it.state.isFinished } -> EtatTravail.EN_ATTENTE
                        else -> EtatTravail.INACTIF
                    }
                }
    }
}
