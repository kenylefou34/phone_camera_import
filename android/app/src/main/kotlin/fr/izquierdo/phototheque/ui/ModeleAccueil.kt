package fr.izquierdo.phototheque.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.reseau.Fabrique
import fr.izquierdo.phototheque.reseau.ServeurRevoqueException
import fr.izquierdo.phototheque.synchro.Orchestrateur
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
    private val _etat = MutableStateFlow(EtatSynchro())
    val etat = _etat.asStateFlow()

    /** Lot 1 : dossiers en dur. L'écran de choix arrive au lot 2. Publics
     *  parce que l'écran de détail les confronte à ce qui existe vraiment sur
     *  le téléphone : un dossier codé en dur mais absent est une sauvegarde
     *  qui réussit à vide. */
    val dossiersSauvegardes = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp")

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
     * Lance une synchronisation. Rien de ce qui se passe à l'intérieur ne doit
     * pouvoir fermer l'application : une coroutine qui lève tue le processus,
     * là où la conception promet un bandeau.
     */
    fun synchroniser() {
        val charge = coffre.charge() ?: return
        _etat.value = _etat.value.copy(enCours = true, serveurIntrouvable = false,
                                       erreur = null, permissionRefusee = false)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val serveur = Fabrique.serveur(getApplication(), charge)
                if (serveur == null) {
                    // Pas à la maison : ce n'est PAS une panne. Ni notification,
                    // ni remise à zéro du compteur de jours.
                    _etat.value = _etat.value.copy(enCours = false, serveurIntrouvable = true)
                    return@launch
                }
                // Ce que le téléphone contient VRAIMENT, relevé avant de
                // conclure : si un des dossiers codés en dur n'existe pas, la
                // synchro réussit avec zéro média et seule cette liste le dit.
                _etat.value = _etat.value.copy(dossiersVus = depot.dossiers())
                val bilan = Orchestrateur(depot, serveur).synchroniser(dossiersSauvegardes)
                // Le jeton ne redeviendra jamais valable : garder le coffre plein
                // ferait revenir sur l'accueil au prochain lancement, avec un
                // jeton mort et aucune explication.
                if (bilan.revoque) coffre.oublier()
                // Réussite = aucun échec local ET le serveur a rangé sans erreur.
                // Ignorer `errors` ferait afficher « sauvegardé » alors que le
                // serveur n'a fait avancer AUCUN horizon (contrat, section 4.4).
                val reussite = bilan.echecs == 0 && !bilan.revoque &&
                               (bilan.bilanServeur["errors"] ?: 0.0) == 0.0
                if (reussite) memoire.enregistrerReussite(System.currentTimeMillis())
                _etat.value = _etat.value.copy(
                    enCours = false,
                    dernierBilan = bilan,
                    revoque = bilan.revoque,
                    // Le coffre vient d'être vidé (oublier()) : l'écran
                    // d'appairage doit reprendre la main, pas rester sur un
                    // accueil orphelin.
                    appaire = !bilan.revoque,
                    accesPartiel = depot.accesPartiel(),
                    // Relue de la mémoire, jamais recalculée ici : c'est elle
                    // qui fait foi d'un lancement à l'autre.
                    derniereReussiteMs = memoire.derniereReussiteMs(),
                )
            } catch (e: ServeurRevoqueException) {
                // Le serveur a RÉPONDU et nous refuse. Seul un nouveau QR
                // débloque : on efface l'appairage et on le dit.
                coffre.oublier()
                _etat.value = _etat.value.copy(
                    enCours = false, revoque = true, appaire = false)
            } catch (e: SecurityException) {
                // Permission retirée dans les Réglages : bandeau permanent,
                // jamais une fermeture brutale.
                _etat.value = _etat.value.copy(enCours = false, permissionRefusee = true)
            } catch (e: Exception) {
                // Tout le reste est une panne VISIBLE, pas un silence.
                _etat.value = _etat.value.copy(
                    enCours = false, erreur = e.message ?: e.javaClass.simpleName)
            }
        }
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
