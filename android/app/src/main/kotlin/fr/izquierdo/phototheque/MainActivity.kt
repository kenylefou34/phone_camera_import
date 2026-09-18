package fr.izquierdo.phototheque

import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import fr.izquierdo.phototheque.ui.EcranAccueil
import fr.izquierdo.phototheque.ui.EcranAppairage
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
        ActivityResultContracts.RequestMultiplePermissions()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // READ_MEDIA_* n'existent qu'a partir d'Android 13. En dessous, c'est
        // READ_EXTERNAL_STORAGE qu'il faut demander : la reclamer a l'envers ne
        // donne AUCUN acces, et Depot ne verrait alors que les medias crees par
        // l'application elle-meme — panne silencieuse, pas un plantage.
        permissions.launch(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
                arrayOf(android.Manifest.permission.READ_MEDIA_IMAGES,
                        android.Manifest.permission.READ_MEDIA_VIDEO)
            else
                arrayOf(android.Manifest.permission.READ_EXTERNAL_STORAGE))

        setContent {
            MaterialTheme {
                val etat by modele.etat.collectAsStateWithLifecycle()
                var detail by remember { mutableStateOf(false) }
                when {
                    !etat.appaire -> EcranAppairage(
                        qrInvalide = etat.qrInvalide,
                        revoque = etat.revoque,
                        surScanner = {
                            scanner.launch(ScanOptions().setPrompt(
                                "Scannez le QR affiché sur la page du serveur"))
                        })
                    detail -> EcranDetail(etat)
                    else -> EcranAccueil(etat, System.currentTimeMillis(),
                        surSynchroniser = modele::synchroniser,
                        surVoirDetail = { detail = true })
                }
            }
        }
    }
}
