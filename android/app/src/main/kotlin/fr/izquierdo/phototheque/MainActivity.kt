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
import fr.izquierdo.phototheque.synchro.TravailSynchro
import fr.izquierdo.phototheque.ui.EcranAccueil
import fr.izquierdo.phototheque.ui.EcranAppairage
import fr.izquierdo.phototheque.ui.EcranAvancement
import fr.izquierdo.phototheque.ui.EcranDetail
import fr.izquierdo.phototheque.ui.ModeleAccueil

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
                // rememberSaveable et non remember : l'ecran de detail
                // retombait sur l'accueil a chaque rotation (issue #24).
                var detail by rememberSaveable { mutableStateOf(false) }

                // Sans ce BackHandler, le bouton retour du systeme FERMAIT
                // l'application depuis l'ecran de detail, en perdant le
                // dernier bilan (issue #24). `avancement == null` en plus :
                // sinon, pendant une synchro, un premier retour eteignait
                // `detail` sans rien changer a l'ecran (EcranAvancement reste
                // affiche), et le SECOND fermait l'application.
                BackHandler(enabled = detail && avancement == null) { detail = false }

                when {
                    !etat.appaire -> EcranAppairage(
                        qrInvalide = etat.qrInvalide,
                        revoque = etat.revoque,
                        surScanner = {
                            scanner.launch(ScanOptions().setPrompt(
                                "Scannez le QR affiché sur la page du serveur"))
                        })
                    avancement != null -> EcranAvancement(
                        avancement!!, surInterrompre = modele::interrompre)
                    detail -> EcranDetail(etat, TravailSynchro.DOSSIERS_SAUVEGARDES)
                    else -> EcranAccueil(etat, System.currentTimeMillis(),
                        surSynchroniser = modele::synchroniser,
                        // Le travail peut etre EN ATTENTE d'un reseau : aucun
                        // avancement n'est publie, donc aucun autre ecran ne
                        // propose d'en sortir.
                        surInterrompre = modele::interrompre,
                        surVoirDetail = { detail = true })
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
