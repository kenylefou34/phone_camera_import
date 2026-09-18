package fr.izquierdo.phototheque

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
import fr.izquierdo.phototheque.ui.EcranDetail
import fr.izquierdo.phototheque.ui.ModeleAccueil

class MainActivity : ComponentActivity() {

    private val modele: ModeleAccueil by viewModels()

    private val scanner = registerForActivityResult(ScanContract()) { resultat ->
        resultat.contents?.let { modele.enregistrerAppairage(it) }
    }

    private val permissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        permissions.launch(arrayOf(
            android.Manifest.permission.READ_MEDIA_IMAGES,
            android.Manifest.permission.READ_MEDIA_VIDEO))

        setContent {
            MaterialTheme {
                val etat by modele.etat.collectAsStateWithLifecycle()
                var detail by remember { mutableStateOf(false) }
                when {
                    !modele.estAppaire() || etat.revoque -> {
                        LaunchedEffect(Unit) {
                            scanner.launch(ScanOptions().setPrompt(
                                "Scannez le QR affiché sur la page du serveur"))
                        }
                    }
                    detail -> EcranDetail(etat)
                    else -> EcranAccueil(etat, System.currentTimeMillis(),
                        surSynchroniser = modele::synchroniser,
                        surVoirDetail = { detail = true })
                }
            }
        }
    }
}
