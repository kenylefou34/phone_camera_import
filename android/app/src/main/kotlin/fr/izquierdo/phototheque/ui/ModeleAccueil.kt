package fr.izquierdo.phototheque.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.synchro.TravailSynchro
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
    private val _etat = MutableStateFlow(EtatSynchro())
    val etat = _etat.asStateFlow()

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

        viewModelScope.launch {
            TravailSynchro.derniereIssue.collect { issue ->
                if (issue == null) return@collect
                // Les CINQ pannes passent par ici. Ne lire que `bilan`
                // laisserait trois d'entre elles sans message : un serveur
                // introuvable, une revocation levee avant tout bilan, et une
                // panne generique sortent toutes AVANT qu'un bilan existe.
                val base = issue.bilan?.let {
                    _etat.value.apresSynchro(
                        it,
                        accesPartiel = depot.accesPartiel(),
                        accesRefuse = depot.accesRefuse(),
                        derniereReussiteMs = memoire.derniereReussiteMs(),
                    )
                } ?: _etat.value.copy(
                    enCours = false,
                    // Sans ces deux lignes, une permission retiree EN PLEINE
                    // synchro (donc jamais relue par `apresSynchro`, qui ne
                    // s'execute que si un bilan existe) resterait invisible
                    // jusqu'au prochain `onResume` : l'ecran afficherait
                    // « La sauvegarde a echoue » au lieu du bandeau juste.
                    permissionRefusee = depot.accesRefuse(),
                    accesPartiel = depot.accesPartiel(),
                )
                _etat.value = base.copy(
                    serveurIntrouvable = issue.serveurIntrouvable,
                    erreur = issue.erreur,
                    revoque = issue.revoque,
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
                )
            }
        }

        // Reflete l'etat REEL de WorkManager, pas un drapeau pose a la main :
        // entre l'appui sur « Sauvegarder » et la premiere publication
        // d'avancement (3 a 13 s, decouverte reseau comprise), et dans le cas
        // « pas de reseau du tout » qui ne publie jamais rien, c'etait sinon
        // le seul retour possible a l'utilisateur qui manquait.
        viewModelScope.launch {
            TravailSynchro.enCours(application).collect { enCours ->
                _etat.value = _etat.value.copy(enCours = enCours)
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
        _etat.value = _etat.value.copy(appaire = true, qrInvalide = false, revoque = false)
        return true
    }
}
