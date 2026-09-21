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
                } ?: _etat.value.copy(enCours = false)
                _etat.value = base.copy(
                    serveurIntrouvable = issue.serveurIntrouvable,
                    erreur = issue.erreur,
                    revoque = issue.revoque,
                    appaire = !issue.revoque,
                    // Conserve APRES la synchro : c'est la seule liste qui
                    // revele un dossier suivi mais absent du telephone, et
                    // l'avancement qui la portait vient d'etre efface.
                    dossiersVus = issue.dossiersVus.ifEmpty { _etat.value.dossiersVus },
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
