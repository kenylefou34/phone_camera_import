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
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

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
        // Le verrou AVANT tout le reste : la file manuelle (« synchro ») et
        // la file automatique (« synchro-auto ») peuvent démarrer en même
        // temps (voir VerrouSynchro), et tout ce qui suit touche un état
        // partagé par TOUTE exécution. Si une autre exécution tient déjà le
        // verrou, elle publie déjà son propre avancement : on ressort sans
        // rien toucher, ce n'est donc pas un silence, seulement une
        // exécution de trop.
        if (!VerrouSynchro.tenter()) return Result.success()

        // Retenu au fil des publications de l'orchestrateur : c'est la seule
        // source de `dossiersVus`, et sans cette variable la valeur serait
        // perdue des que `_avancement` repasse a null en fin de course.
        // Part de `null` (jamais publie), pas d'une carte vide : sinon une
        // panne survenue AVANT la premiere publication se lirait comme un
        // « MediaStore n'a rien rendu » qu'elle n'a jamais constate.
        //
        // Déclarées ICI, avant le `try`, et non dedans : les blocs `catch`
        // plus bas les lisent, et une variable déclarée À L'INTÉRIEUR d'un
        // `try` n'est pas visible depuis son `catch` (scope Kotlin/JVM).
        var dossiersVus: Map<String, Int>? = null
        // Le bilan REEL, retenu au vol : une annulation empeche `withContext`
        // de le rendre (voir le catch de CancellationException), et sans lui
        // l'ecran annoncerait « 0 envoyes » apres vingt paquets valides.
        var bilanPartiel: Bilan? = null

        // Tout le reste est sous `try`, la préparation ET les remises à
        // zéro comprises — pas seulement `setForeground` (qui lève sur
        // Android 12+ quand le démarrage d'un service de premier plan depuis
        // l'arrière-plan est restreint, exactement le cas d'une reprise
        // automatique, application fermée). Le `finally` ne libère
        // `VerrouSynchro` que pour ce qui est SOUS le `try` : si les trois
        // premières lignes ci-dessous restaient avant son ouverture et que
        // l'une levait, le verrou ne serait plus JAMAIS relâché — plus
        // aucune synchronisation, ni manuelle ni automatique, jusqu'au
        // prochain redémarrage du processus. Pire mode de panne de ce
        // fichier, et silencieux comme les autres qu'il corrige déjà.
        try {
            // `_derniereIssue` est un StateFlow de companion object, donc de
            // la duree de vie du processus : sans cette remise a zero, un
            // nouveau collecteur (ecran recree, nouvelle synchro) rejouerait
            // l'issue de l'execution PRECEDENTE - un vieux bandeau d'erreur
            // qui reapparait.
            _derniereIssue.value = null
            // Une execution neuve n'a recu aucun ordre d'arret. Sans cette
            // remise a zero, un arret demande lors de la synchro PRECEDENTE
            // ferait annoncer « interrompue » a celle-ci.
            arretDemande = false
            // `contexte` reste local au `try` : sa seule utilisation en
            // dehors (l'ancien `catch (ServeurRevoqueException)`) a été
            // remplacée par `applicationContext` directement, précisément
            // pour ne pas avoir à le sortir d'ici.
            val contexte = applicationContext

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
            //
            // La même condition borne l'écriture de `debutApplique` plus bas :
            // une reprise coupée en deux (interrompue, ou révoquée, ou dont le
            // serveur a raté le rangement) doit se rejouer entièrement la
            // prochaine fois, pas être considérée acquise.
            //
            // `vus` est calculé ici, avant la règle, parce qu'elle en a
            // besoin : une synchronisation qui n'a couvert AUCUN dossier
            // (tout décoché, ou le seul dossier coché déplacé par WhatsApp)
            // n'a rien sauvegardé et ne doit pas rallumer le vert. Il ressert
            // tel quel pour `apresSynchro`, plus bas.
            val vus = dossiersVus?.keys.orEmpty()
            val reussiteComplete = !bilan.interrompu && EtatSynchro.estUneReussite(
                bilan, depot.accesRefuse(),
                dossiersRetenus = Choix.dossiersASauvegarder(reglages, vus).size)
            if (reussiteComplete) {
                Memoire(contexte).enregistrerReussite(System.currentTimeMillis())
            }

            // Les dossiers entrés par une coche récursive depuis la dernière
            // synchronisation, et la date de début dont la reprise vient
            // d'être menée à son terme (`debutApplique`, tâche 7). La
            // décision de ce qu'il faut écrire est extraite dans
            // `Reglages.apresSynchro` — seule pièce testable sur la JVM de ce
            // geste, voir son KDoc pour le détail des gardes — et appelée ici
            // en une seule lecture, un seul appel, une seule écriture : deux
            // `ecrire()` bâtis chacun sur sa propre lecture s'écraseraient
            // l'un l'autre selon l'ordre.
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
            // N'écrit rien si ni l'un ni l'autre champ ne peut changer : une
            // permission média retirée fait rendre `lister()` une liste vide,
            // la synchro « réussit » quand même (aucun média à envoyer n'est
            // pas un échec), et sans cette garde `dossiersConnus` repartirait
            // à zéro — la prochaine synchro, permission revenue, annoncerait
            // alors TOUS les dossiers récursifs comme nouveaux, à tort.
            if (vus.isNotEmpty() || reussiteComplete) {
                magasin.ecrire(avant.apresSynchro(
                    vus,
                    // Un accès PARTIEL (Android 14+, Depot.accesPartiel) ne
                    // doit JAMAIS consommer une reprise : `lister()` ne rend
                    // alors que les médias que l'utilisateur a sélectionnés,
                    // la synchro « réussit » quand même, et `debutApplique`
                    // serait rangé à tort — l'accès complet accordé plus
                    // tard ne reproposerait alors plus jamais les médias
                    // restés hors sélection. `reussiteComplete` seul reste
                    // correct pour `Memoire.enregistrerReussite` ci-dessus :
                    // un accès partiel a déjà son propre état permanent
                    // (`EtatSynchro.accesPartiel`), pas le compteur de jours.
                    reussiteComplete && !depot.accesPartiel(),
                    reglages.debutJour,
                ))
            }

            _derniereIssue.value = IssueSynchro(
                bilan = bilan.pourLEcran(), revoque = bilan.revoque, dossiersVus = dossiersVus,
                dossiersNouveaux = nouveaux)
            return if (Reprise.fautIlRelancer(bilan) && runAttemptCount < TENTATIVES_MAX)
                Result.retry() else Result.success()

        } catch (e: ServeurRevoqueException) {
            // `applicationContext` directement, et non la `contexte` locale
            // du `try` : elle n'est plus visible ici depuis qu'elle est
            // déclarée à l'intérieur (voir le commentaire au-dessus du `try`).
            Coffre(applicationContext).oublier()
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
            // Symétrique du `tenter()` du début : on n'atteint ce `finally`
            // que si on a bien pris le verrou (le repli `!VerrouSynchro.tenter()`
            // ressort avant), donc le libérer ici est toujours correct.
            VerrouSynchro.liberer()
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

        // Nom distinct de NOM : le travail périodique (planifier) et le
        // travail unique (lancer) ne doivent jamais se marcher dessus - deux
        // noms identiques feraient qu'annuler l'un annulerait aussi l'autre.
        private const val NOM_PERIODIQUE = "synchro-auto"

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

        /**
         * Annule LES DEUX files, pas seulement la manuelle.
         *
         * Sans ça, le bouton « Interrompre » serait muet sur une
         * synchronisation automatique — précisément le cas où l'utilisateur
         * voudra le plus s'en servir, puisqu'elle a démarré sans qu'il l'ait
         * demandée. `arretDemande` est un seul drapeau, lu par les deux
         * files quelle que soit celle qui tourne : il n'y a donc rien à
         * distinguer ici.
         *
         * Et REPROGRAMME l'automatique derrière. `cancelUniqueWork` ne
         * suspend pas la passe en cours : il **détruit la chaîne
         * périodique**. Sans cette dernière ligne, un appui sur
         * « Interrompre » déprogrammerait la sauvegarde automatique pour
         * toujours, pendant que l'interrupteur des réglages continuerait
         * d'afficher « actif » — la panne muette que ce sous-projet existe
         * pour supprimer, exactement celle que `enregistrerAppairage` évite
         * déjà avec le même appel.
         */
        fun interrompre(context: Context) {
            // Pose AVANT l'annulation : c'est ce drapeau, et non `isStopped`,
            // qui distingue un arret demande d'une coupure subie.
            arretDemande = true
            val gestionnaire = WorkManager.getInstance(context)
            gestionnaire.cancelUniqueWork(NOM)
            gestionnaire.cancelUniqueWork(NOM_PERIODIQUE)
            // Relu des préférences, et non d'un état en mémoire : ce code
            // tourne aussi depuis le bouton de la NOTIFICATION, application
            // fermée, où aucun modèle de vue n'existe.
            //
            // L'ordre compte, et il est garanti : `cancelUniqueWork` et
            // `enqueueUniquePeriodicWork` sont tous deux postés sur le MÊME
            // exécuteur sérialisé de WorkManager, donc l'annulation est
            // traitée avant la replanification. Si elle ne l'était pas, le
            // `KEEP` de `planifier` verrait un travail encore vivant, ne
            // ferait rien, et l'annulation détruirait la chaîne juste après.
            planifier(context, MagasinReglages(context).lire().auto, apresUnArret = true)
        }

        /**
         * Programme, ou déprogramme, la sauvegarde automatique.
         *
         * Six heures n'est PAS un réveil à heure fixe : c'est « au plus une
         * fois par tranche de six heures, dès que les conditions sont
         * réunies ». Android regroupe ces réveils (mode Doze), le délai peut
         * donc glisser à sept ou huit heures si le téléphone dort — jamais
         * se déclencher plus tôt. En pratique, avec ces deux contraintes,
         * cela donne une passe par nuit, au branchement du téléphone à la
         * maison.
         *
         * `setRequiresCharging(true)` n'est pas un luxe : un gros rattrapage
         * lit des dizaines de milliers d'empreintes, c'est du calcul, et le
         * faire sur batterie en pleine journée viderait le téléphone.
         *
         * `UNMETERED` et non `CONNECTED` : le rattrapage peut représenter des
         * dizaines de gigaoctets, et l'utilisateur ne s'attend pas à les voir
         * partir sur son forfait.
         */
        fun planifier(context: Context, actif: Boolean, apresUnArret: Boolean = false) {
            val gestionnaire = WorkManager.getInstance(context)
            if (!actif) {
                gestionnaire.cancelUniqueWork(NOM_PERIODIQUE)
                return
            }
            val demande = PeriodicWorkRequestBuilder<TravailSynchro>(6, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.UNMETERED)
                    .setRequiresCharging(true)
                    .build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL,
                                    WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
                // Un travail périodique NEUF part dès que ses contraintes sont
                // satisfaites, sans attendre sa première période. Replanifier
                // juste après un arrêt demandé (voir `interrompre`)
                // relancerait donc aussitôt la synchronisation qu'on vient
                // d'arrêter : le téléphone est en charge sur le WiFi de la
                // maison, c'est-à-dire exactement la situation où ce bouton
                // sert. D'où ce délai, et seulement dans ce cas-là : cocher
                // l'interrupteur, lui, doit pouvoir donner une première passe
                // dans la foulée.
                .apply { if (apresUnArret) setInitialDelay(6, TimeUnit.HOURS) }
                .build()
            // KEEP : reprogrammer à chaque ouverture de l'écran remettrait le
            // compteur à zéro, et la passe n'aurait jamais lieu sur un
            // téléphone qu'on ouvre souvent.
            gestionnaire.enqueueUniquePeriodicWork(
                NOM_PERIODIQUE, ExistingPeriodicWorkPolicy.KEEP, demande)
        }

        /** Etat du travail, derive de WorkManager et non d'un drapeau pose a
         *  la main : un travail differe par la contrainte reseau resterait
         *  sinon « en cours » pour toujours, et l'utilisateur n'aurait aucun
         *  retour de son appui. Voir EtatTravail pour la raison des trois
         *  etats actifs.
         *
         *  Suit LES DEUX files, mais ne les traite pas pareil : voir
         *  [EtatTravail.combiner], qui porte la regle et les tests. Tout ce
         *  qui reste ici est la traduction d'un `WorkInfo` en trois valeurs —
         *  la seule part que rien ne peut verifier sur la JVM. */
        fun etatTravail(context: Context): Flow<EtatTravail> {
            val gestionnaire = WorkManager.getInstance(context)
            return combine(
                gestionnaire.getWorkInfosForUniqueWorkFlow(NOM),
                gestionnaire.getWorkInfosForUniqueWorkFlow(NOM_PERIODIQUE),
            ) { manuel, automatique ->
                EtatTravail.combiner(manuel.map { it.suivi() }, automatique.map { it.suivi() })
            }
        }

        private fun WorkInfo.suivi() = SuiviTravail(
            enCours = state == WorkInfo.State.RUNNING,
            termine = state.isFinished,
            tentatives = runAttemptCount)
    }
}
