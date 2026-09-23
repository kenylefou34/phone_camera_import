package fr.izquierdo.phototheque

import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.ui.Ecran
import fr.izquierdo.phototheque.ui.EcranAccueil
import fr.izquierdo.phototheque.ui.EcranAppairage
import fr.izquierdo.phototheque.ui.EcranAvancement
import fr.izquierdo.phototheque.ui.EcranDetail
import fr.izquierdo.phototheque.ui.EcranDossiers
import fr.izquierdo.phototheque.ui.EcranReglages
import fr.izquierdo.phototheque.ui.EcranSauvegarde
import fr.izquierdo.phototheque.ui.ModeleAccueil
import fr.izquierdo.phototheque.ui.Navigation

class MainActivity : ComponentActivity() {

    private val modele: ModeleAccueil by viewModels()

    private val scanner = registerForActivityResult(ScanContract()) { resultat ->
        // La valeur de retour est EXPLOITEE : un QR invalide doit produire un
        // message, pas un silence.
        resultat.contents?.let { modele.enregistrerAppairage(it) }
    }

    private val permissions = registerForActivityResult(
        // Le resultat est EXPLOITE : jete, un refus d'acces aux photos ne
        // produisait aucun message, et l'application se contentait de ne rien
        // sauvegarder en silence.
        ActivityResultContracts.RequestMultiplePermissions()) { modele.rafraichirPermissions() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // READ_MEDIA_* n'existent qu'a partir d'Android 13. En dessous, c'est
        // READ_EXTERNAL_STORAGE qu'il faut demander : la reclamer a l'envers ne
        // donne AUCUN acces, et Depot ne verrait alors que les medias crees par
        // l'application elle-meme — panne silencieuse, pas un plantage.
        permissions.launch(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
                // POST_NOTIFICATIONS est demandee ICI et pas ailleurs : sans
                // elle, le service de premier plan demarre mais sa
                // notification reste invisible, et l'utilisateur n'a plus
                // aucun moyen de voir ou d'arreter une synchro en cours.
                arrayOf(android.Manifest.permission.READ_MEDIA_IMAGES,
                        android.Manifest.permission.READ_MEDIA_VIDEO,
                        android.Manifest.permission.POST_NOTIFICATIONS)
            else
                arrayOf(android.Manifest.permission.READ_EXTERNAL_STORAGE))

        setContent {
            MaterialTheme {
                val etat by modele.etat.collectAsStateWithLifecycle()
                val avancement by modele.avancement.collectAsStateWithLifecycle()
                val reglages by modele.reglages.collectAsStateWithLifecycle()
                // Un Depot local, distinct de celui de ModeleAccueil (privé) :
                // seul l'écran des dossiers en a besoin, pour l'aperçu à la
                // demande — ModeleAccueil n'a rien d'autre à en faire.
                val depot = remember { Depot(applicationContext) }
                // rememberSaveable et non remember : l'écran affiché retombait
                // sur l'accueil à chaque rotation (issue #24).
                var demande by rememberSaveable { mutableStateOf(Ecran.ACCUEIL) }
                val affiche = Navigation.ecranAffiche(
                    demande, appaire = etat.appaire, synchroEnCours = avancement != null)

                // Le retour est calculé, plus deviné : à sept destinations, la
                // cascade de booléens du lot 1 laissait des états
                // inatteignables par le bouton retour.
                BackHandler(enabled = Navigation.retour(affiche) != null) {
                    Navigation.retour(affiche)?.let { demande = it }
                }

                when (affiche) {
                    Ecran.APPAIRAGE -> EcranAppairage(
                        qrInvalide = etat.qrInvalide,
                        revoque = etat.revoque,
                        surScanner = {
                            scanner.launch(
                                ScanOptions()
                                    .setPrompt("Scannez le QR affiché sur la page du serveur")
                                    // Sans ceci, zxing verrouille sa camera en
                                    // PAYSAGE : `orientationLocked` vaut true par
                                    // defaut et l'activite de capture est declaree
                                    // en paysage dans la bibliotheque. Il fallait
                                    // donc tourner le telephone pour scanner un QR
                                    // affiche a l'ecran d'un ordinateur — signale
                                    // par le mainteneur au premier appairage reel,
                                    // le 23/09.
                                    .setOrientationLocked(false))
                        })
                    Ecran.ACCUEIL ->
                        if (avancement != null) EcranAvancement(
                            avancement!!, reglages, surInterrompre = modele::interrompre)
                        else EcranAccueil(etat, reglages, System.currentTimeMillis(),
                            surSynchroniser = modele::synchroniser,
                            // Le travail peut etre EN ATTENTE d'un reseau : aucun
                            // avancement n'est publie, donc aucun autre ecran ne
                            // propose d'en sortir.
                            surInterrompre = modele::interrompre,
                            surVoirDetail = { demande = Ecran.DETAIL },
                            surReglages = { demande = Ecran.REGLAGES })
                    Ecran.DETAIL -> EcranDetail(etat, reglages)
                    Ecran.REGLAGES -> EcranReglages(
                        surDossiers = { demande = Ecran.DOSSIERS },
                        surSauvegarde = { demande = Ecran.SAUVEGARDE },
                        surAppareil = { demande = Ecran.APPAREIL })
                    Ecran.DOSSIERS -> EcranDossiers(
                        dossiersVus = etat.dossiersVus,
                        reglages = reglages,
                        depot = depot,
                        surCoche = modele::changerCoche)
                    Ecran.SAUVEGARDE -> EcranSauvegarde(
                        reglages = reglages,
                        depot = depot,
                        surChangerDebut = modele::changerDebut,
                        surChangerFin = modele::changerFin,
                        surChangerAuto = modele::changerAuto)
                    // Écrit à la tâche 11.
                    Ecran.APPAREIL -> EcranReglages(
                        surDossiers = {}, surSauvegarde = {}, surAppareil = {})
                }
            }
        }
    }

    /**
     * L'utilisateur peut avoir modifié l'autorisation dans les réglages Android
     * pendant que l'application était en arrière-plan, ou n'avoir rouvert
     * l'accès qu'à une sélection de photos. Sans cette relecture, le bandeau
     * resterait affiché — ou, pire, absent — jusqu'à la synchro suivante.
     */
    override fun onResume() {
        super.onResume()
        modele.rafraichirPermissions()
    }
}
