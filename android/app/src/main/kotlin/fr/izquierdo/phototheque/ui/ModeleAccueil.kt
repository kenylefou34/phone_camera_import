package fr.izquierdo.phototheque.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.reseau.Fabrique
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
    private val _etat = MutableStateFlow(EtatSynchro())
    val etat = _etat.asStateFlow()

    /** Lot 1 : dossiers en dur. L'écran de choix arrive au lot 2. */
    private val dossiers = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp")

    init {
        _etat.value = _etat.value.copy(appaire = coffre.charge() != null)
    }

    fun synchroniser() {
        val charge = coffre.charge() ?: return
        _etat.value = _etat.value.copy(enCours = true, serveurIntrouvable = false)
        viewModelScope.launch(Dispatchers.IO) {
            val serveur = Fabrique.serveur(getApplication(), charge)
            if (serveur == null) {
                // Pas à la maison : ce n'est PAS une panne. Ni notification, ni
                // remise à zéro du compteur de jours.
                _etat.value = _etat.value.copy(enCours = false, serveurIntrouvable = true)
                return@launch
            }
            val bilan = Orchestrateur(depot, serveur).synchroniser(dossiers)
            if (bilan.revoque) coffre.oublier()
            _etat.value = _etat.value.copy(
                enCours = false,
                dernierBilan = bilan,
                revoque = bilan.revoque,
                // Le coffre vient d'être vidé (oublier()) : l'écran d'appairage
                // doit reprendre la main, pas rester sur un accueil orphelin.
                appaire = !bilan.revoque,
                accesPartiel = depot.accesPartiel(),
                // Réussite = aucun échec. Un refus d'extension n'en est pas un.
                derniereReussiteMs = if (bilan.echecs == 0 && !bilan.revoque)
                    System.currentTimeMillis() else _etat.value.derniereReussiteMs,
            )
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
