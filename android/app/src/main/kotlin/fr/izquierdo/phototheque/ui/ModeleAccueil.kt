package fr.izquierdo.phototheque.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.reseau.ClientServeur
import fr.izquierdo.phototheque.reseau.Decouverte
import fr.izquierdo.phototheque.reseau.Fabrique
import fr.izquierdo.phototheque.synchro.Coche
import fr.izquierdo.phototheque.synchro.Desappairage
import fr.izquierdo.phototheque.synchro.EtatTravail
import fr.izquierdo.phototheque.synchro.TravailSynchro
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Modèle de vue de l'écran d'accueil. Porte l'état affiché ([etat]) et les
 * deux actions que l'utilisateur peut déclencher : synchroniser, et
 * enregistrer un appairage scanné.
 */
class ModeleAccueil(application: Application) : AndroidViewModel(application) {

    private val coffre = Coffre(application)
    private val depot = Depot(application)
    private val memoire = Memoire(application)
    private val magasin = MagasinReglages(application)
    private val _etat = MutableStateFlow(EtatSynchro())
    val etat = _etat.asStateFlow()

    /** Les réglages choisis par l'utilisateur, relus au démarrage. */
    private val _reglages = MutableStateFlow(magasin.lire())
    val reglages = _reglages.asStateFlow()

    /** L'avancement publié par le travail de fond, null quand rien ne tourne. */
    val avancement = TravailSynchro.avancement

    init {
        // Le compteur de jours est relu du disque : Android tue l'application
        // en permanence, et un compteur reparti de zéro afficherait « Jamais
        // sauvegardé » en rouge après une synchro parfaite.
        _etat.value = _etat.value.copy(
            appaire = coffre.charge() != null,
            derniereReussiteMs = memoire.derniereReussiteMs(),
        )
        // Dès le lancement, pas seulement en fin de synchro : la conception
        // veut ces deux avertissements affichés EN PERMANENCE. Ne les calculer
        // qu'après une synchronisation les rendait invisibles à qui ouvre
        // l'application et la referme.
        rafraichirPermissions()
        // Reprogramme le travail périodique à chaque démarrage, pas seulement
        // au moment où l'utilisateur coche. PAS pour survivre à une
        // réinstallation : celle-ci efface les préférences ET la base
        // WorkManager ensemble, donc `_reglages.value.auto` reviendrait de
        // toute façon à `false` — ce garde-fou n'y servirait à rien. La
        // vraie raison est plus étroite : le système ou le fabricant du
        // téléphone peut effacer la base de WorkManager SEULE (nettoyage
        // agressif de batterie, mise à jour du composant) sans toucher aux
        // préférences de l'application. Sans cet appel, un utilisateur qui a
        // coché l'automatique verrait alors le réglage rester affiché comme
        // actif tout en n'étant plus programmé nulle part — une automatique
        // qui s'est éteinte sans le dire. `ExistingPeriodicWorkPolicy.KEEP`
        // rend cet appel sans effet quand le travail existe déjà.
        TravailSynchro.planifier(getApplication(), _reglages.value.auto)

        viewModelScope.launch {
            TravailSynchro.derniereIssue.collect { issue ->
                if (issue == null) return@collect
                // Les CINQ pannes passent par ici. Ne lire que `bilan`
                // laisserait trois d'entre elles sans message : un serveur
                // introuvable, une revocation levee avant tout bilan, et une
                // panne generique sortent toutes AVANT qu'un bilan existe.

                // Lu UNE seule fois : la reponse sert a trois endroits plus
                // bas, et trois lectures pourraient se contredire.
                val accesRefuse = depot.accesRefuse()
                val base = issue.bilan?.let {
                    _etat.value.apresSynchro(
                        it,
                        accesPartiel = depot.accesPartiel(),
                        accesRefuse = accesRefuse,
                        derniereReussiteMs = memoire.derniereReussiteMs(),
                    )
                } ?: _etat.value.copy(
                    enCours = false,
                    // Sans ces deux lignes, une permission retiree EN PLEINE
                    // synchro (donc jamais relue par `apresSynchro`, qui ne
                    // s'execute que si un bilan existe) resterait invisible
                    // jusqu'au prochain `onResume` : l'ecran afficherait
                    // « La sauvegarde a echoue » au lieu du bandeau juste.
                    permissionRefusee = accesRefuse,
                    accesPartiel = depot.accesPartiel(),
                )
                _etat.value = base.copy(
                    serveurIntrouvable = issue.serveurIntrouvable,
                    // Une permission retiree a DEJA son bandeau, qui dit quoi
                    // faire. Y ajouter « La sauvegarde a echoue : Permission
                    // Denial… » donnerait deux messages pour une seule panne,
                    // dont un que personne ne peut exploiter.
                    erreur = if (accesRefuse) null else issue.erreur,
                    // Meme source de verite qu'`appaire` : une revocation
                    // reelle vide le coffre AVANT de publier l'issue, donc
                    // coffre vide = revocation en cours. Lire `issue.revoque`
                    // seul rejouerait une revocation perimee apres un rescan
                    // de QR, et afficherait « revoque » sur un telephone
                    // fraichement reappaire.
                    revoque = issue.revoque && coffre.charge() == null,
                    // Deduit du coffre, pas de `issue.revoque` : `derniereIssue`
                    // est un StateFlow de companion object, donc de la duree de
                    // vie du PROCESSUS. Une revocation rescannee puis
                    // l'application relancee (activite recreee, processus
                    // vivant) rejouerait sinon une vieille revocation sur un
                    // coffre pourtant plein.
                    appaire = coffre.charge() != null,
                    // Conserve APRES la synchro : c'est la seule liste qui
                    // revele un dossier suivi mais absent du telephone, et
                    // l'avancement qui la portait vient d'etre efface. `null`
                    // (jamais publie) et carte vide (regarde, rien trouve) ne
                    // doivent jamais etre confondus : `?:` et non `ifEmpty`.
                    dossiersVus = issue.dossiersVus ?: _etat.value.dossiersVus,
                    // Pas de repli sur l'ancienne valeur, contrairement à
                    // dossiersVus : ce signal est propre à CETTE issue (seule
                    // la fin réussie de doWork le calcule, TravailSynchro.kt).
                    // Le conserver d'une synchro à l'autre ferait ressurgir un
                    // avertissement périmé après une synchro qui a échoué.
                    dossiersNouveaux = issue.dossiersNouveaux,
                )
            }
        }

        // Reflete l'etat REEL de WorkManager, pas un drapeau pose a la main :
        // entre l'appui sur « Sauvegarder » et la premiere publication
        // d'avancement (3 a 13 s, decouverte reseau comprise), et dans le cas
        // « pas de reseau du tout » qui ne publie jamais rien, c'etait sinon
        // le seul retour possible a l'utilisateur qui manquait.
        viewModelScope.launch {
            TravailSynchro.etatTravail(application).collect { travail ->
                _etat.value = _etat.value.copy(
                    enCours = travail != EtatTravail.INACTIF,
                    // Trois états actifs, trois phrases distinctes : sans
                    // cette séparation l'écran dirait « en attente d'un
                    // réseau » pendant les 3 à 13 s de recherche du serveur
                    // qui suivent chaque appui, et pendant le délai de reprise
                    // qui suit une permission retirée — deux fois faux.
                    enAttenteReseau = travail == EtatTravail.EN_ATTENTE,
                    nouvelleTentative = travail == EtatTravail.NOUVELLE_TENTATIVE,
                )
            }
        }
    }

    /**
     * Relit ce que l'application a le droit de lire. À appeler au lancement, au
     * retour des réglages Android, et après chaque réponse à une demande de
     * permission — dont le résultat était jusqu'ici purement et simplement
     * jeté.
     */
    fun rafraichirPermissions() {
        _etat.value = _etat.value.copy(
            accesPartiel = depot.accesPartiel(),
            permissionRefusee = depot.accesRefuse(),
        )
    }

    /**
     * Demande une synchronisation à Android. Le travail lui survit : ce modèle
     * de vue ne l'exécute plus, il l'observe.
     */
    fun synchroniser() {
        if (coffre.charge() == null) return
        rafraichirPermissions()
        // Le résultat de la synchronisation PRÉCÉDENTE s'efface ici. Sans
        // cela, l'accueil affiche « Sauvegarde en cours… » ET « La sauvegarde
        // a échoué » en même temps : pendant les 3 à 13 s qui précèdent la
        // première publication, et indéfiniment si la contrainte réseau
        // diffère le travail.
        _etat.value = _etat.value.copy(
            erreur = null, serveurIntrouvable = false, dernierBilan = null)
        TravailSynchro.lancer(getApplication())
    }

    fun interrompre() {
        TravailSynchro.interrompre(getApplication())
    }

    /** Vrai si le QR scanne etait bien un appairage. Le resultat doit etre
     *  EXPLOITE : un faux renvoie l'ecran d'appairage avec un message. */
    fun enregistrerAppairage(texteDuQr: String): Boolean {
        val charge = fr.izquierdo.phototheque.appairage.Appairage.lire(texteDuQr)
        if (charge == null) {
            _etat.value = _etat.value.copy(qrInvalide = true)
            return false
        }
        coffre.enregistrer(charge)
        // desappairementNonPrevenu remis à faux : sa bannière parlait de
        // l'ANCIEN serveur, elle n'a plus rien à dire sur celui-ci.
        _etat.value = _etat.value.copy(appaire = true, qrInvalide = false, revoque = false,
                                       desappairementNonPrevenu = false)
        // Un désappairage précédent déprogramme l'automatique SANS toucher
        // aux réglages (`desappairer`, plus bas) : si `reglages.auto` est
        // resté vrai, ce réappairage doit le reprogrammer, sinon
        // l'interrupteur resterait affiché actif alors que plus rien n'est
        // planifié — la panne muette que ce sous-projet existe pour
        // supprimer, et précisément le scénario « désappairer puis
        // rescanner » que cette fonctionnalité écrit.
        TravailSynchro.planifier(getApplication(), _reglages.value.auto)
        return true
    }

    /**
     * Change la coche d'un dossier et persiste aussitôt.
     *
     * Pas de bouton « enregistrer » distinct : un réglage qu'on croit posé et
     * qui se perd (application tuée avant qu'on ne quitte l'écran) serait la
     * panne muette exacte que ce sous-projet existe pour éviter.
     *
     * Relit `magasin.lire()`, pas `_reglages.value` : ce dernier est posé une
     * fois à la construction du modèle de vue et jamais rafraîchi. Le travail
     * de fond écrit `dossiersConnus` et `debutApplique` (tâche 7)
     * directement dans les préférences, sans passer par ce `StateFlow`. Partir
     * de `_reglages.value` réécrirait l'objet entier avec ces champs-là
     * PÉRIMÉS — le geste le plus normal qui soit (cocher un dossier)
     * effacerait alors en silence ce que la synchro venait de noter.
     */
    fun changerCoche(chemin: String, coche: Coche) {
        val r = magasin.lire()
        val nouveau = r.copy(
            dossiersSeuls = if (coche == Coche.DOSSIER) r.dossiersSeuls + chemin
                            else r.dossiersSeuls - chemin,
            dossiersRecursifs = if (coche == Coche.RECURSIVE) r.dossiersRecursifs + chemin
                                else r.dossiersRecursifs - chemin)
        _reglages.value = nouveau
        magasin.ecrire(nouveau)
    }

    /**
     * Change la date de début et persiste aussitôt. `null` l'efface (retour
     * au plancher de l'appairage).
     *
     * Relit `magasin.lire()`, comme `changerCoche` : voir sa doc pour la
     * raison (ne pas écraser `dossiersConnus`/`debutApplique`, écrits par le
     * travail de fond, avec une valeur périmée).
     */
    fun changerDebut(jour: String?) {
        val r = magasin.lire()
        val nouveau = r.copy(debutJour = jour)
        _reglages.value = nouveau
        magasin.ecrire(nouveau)
    }

    /** Change la date de fin et persiste aussitôt. `null` l'efface. */
    fun changerFin(jour: String?) {
        val r = magasin.lire()
        val nouveau = r.copy(finJour = jour)
        _reglages.value = nouveau
        magasin.ecrire(nouveau)
    }

    /**
     * Bascule l'automatique et persiste aussitôt. Passer à `true` efface la
     * date de fin (`Reglages.enAuto`) : c'est à l'écran de le dire au moment
     * où on coche.
     *
     * [TravailSynchro.planifier] a plusieurs appelants dans ce modèle de
     * vue — ce n'est PLUS « deux, et les deux seuls » comme l'affirmait une
     * précédente version de ce commentaire : cette affirmation même est ce
     * qui a longtemps découragé d'ajouter l'appel manquant dans
     * `enregistrerAppairage` (voir sa doc). Ce qui reste vrai, et qui
     * compte : ici, à chaque bascule de la case par l'utilisateur, c'est le
     * SEUL endroit où un changement VOLONTAIRE de `reglages.auto` se
     * traduit en travail programmé ou déprogrammé. Les autres appelants
     * (`init`, `enregistrerAppairage`, `desappairer`) ne font que
     * RECONCILIER le travail planifié avec un `reglages.auto` déjà décidé
     * ailleurs — aucun d'eux ne change ce booléen.
     */
    fun changerAuto(actif: Boolean) {
        val r = magasin.lire()
        val nouveau = if (actif) r.enAuto() else r.copy(auto = false)
        _reglages.value = nouveau
        magasin.ecrire(nouveau)
        TravailSynchro.planifier(getApplication(), actif)
    }

    /**
     * Désappaire ce téléphone : coupe le lien avec le serveur courant.
     *
     * Ce n'est PAS le moyen de tout reprendre — la date de début fait ce
     * travail, sans rescanner de QR et de façon réversible. Son vrai métier
     * est de se dépanner et de changer de serveur : voir [Desappairage] pour
     * la raison qui impose un effacement local INCONDITIONNEL.
     *
     * Construit ici ses propres [ClientServeur] plutôt que de passer par
     * [Fabrique.serveur] : celui-ci rend l'interface `Serveur`, taillée pour
     * `Orchestrateur`, qui n'expose pas `desappairer()` — et exige une charge
     * non nulle que `coffre.charge()` ne garantit pas.
     */
    fun desappairer() {
        viewModelScope.launch(Dispatchers.IO) {
            val resultat = Desappairage.executer(
                prevenirServeur = {
                    coffre.charge()?.let { charge ->
                        val http = Fabrique.client(charge)
                        val court = Fabrique.clientCourt(http)
                        // Comme Fabrique.serveur() (Decouverte.kt) : l'adresse
                        // du NUC change (bail DHCP ordinaire, cf. CLAUDE.md —
                        // .21 puis .31 en deux jours). Se limiter à
                        // `charge.url` ferait échouer CETTE notification à
                        // chaque fois que l'adresse a bougé depuis
                        // l'appairage — le cas le plus courant ici — et le
                        // bandeau mentirait en réclamant une révocation
                        // manuelle d'un serveur pourtant joignable à trois
                        // mètres.
                        (Decouverte.adresses(getApplication()) + charge.url).any { base ->
                            ClientServeur(base, charge.token, http, court).desappairer()
                        }
                    } ?: false
                },
                effacerLocal = {
                    coffre.oublier()
                    // Les réglages restent : ils ne sont pas liés à un
                    // serveur, et les perdre obligerait à tout recocher pour
                    // un simple changement de NUC.
                    TravailSynchro.planifier(getApplication(), actif = false)
                    // Une ancienne réussite ne dit plus rien sur le PROCHAIN
                    // serveur : la garder afficherait « sauvegardé il y a
                    // 2 h » en vert après un changement de NUC qui n'a encore
                    // rien reçu — une fausse réassurance, pire qu'une fausse
                    // alerte, puisqu'elle éteint le seul filet du projet
                    // contre les pannes muettes.
                    memoire.oublier()
                })
            _etat.value = _etat.value.copy(
                appaire = false, revoque = false,
                desappairementNonPrevenu = !resultat.serveurPrevenu,
                // Sans ceci, l'accueil rouvrirait sur « sauvegardé il y a
                // 2 h » le temps que `_etat` soit relu ailleurs : la même
                // fausse réassurance que memoire.oublier() efface sur le
                // disque, mais encore visible en mémoire tant qu'on ne la
                // corrige pas ici aussi.
                derniereReussiteMs = null)
        }
    }
}
