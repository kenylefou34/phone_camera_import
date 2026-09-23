package fr.izquierdo.phototheque.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.medias.Media
import fr.izquierdo.phototheque.synchro.Choix
import fr.izquierdo.phototheque.synchro.Fenetre
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.math.ceil

/**
 * Débit supposé pour estimer la durée de la prochaine reprise après un
 * désappairage — aucune mesure locale n'existe hors d'une synchronisation en
 * cours (voir `synchro.Debit`, dont la fenêtre glissante n'a de sens que
 * PENDANT un envoi). Même ordre de grandeur que celui déjà cité en
 * commentaire dans `reseau.Decouverte` pour une vidéo de plusieurs Go sur un
 * Wi-Fi domestique : une approximation assumée, pas une mesure.
 */
private const val OCTETS_PAR_SECONDE_SUPPOSES = 12_000_000L

/**
 * Écran « Cet appareil » : désappairer pour se dépanner ou changer de
 * serveur. Voir `synchro.Desappairage` pour ce que ce geste fait, et surtout
 * ne fait PAS.
 *
 * Ce que devient le résultat (serveur prévenu ou non) n'est PAS affiché ici :
 * un désappairage réussi fait aussitôt retomber `Navigation` sur l'écran
 * d'appairage (`appaire` passe à faux), qui remplace celui-ci avant qu'un
 * message posé ici ait la moindre chance d'être vu. C'est `EcranAppairage`
 * qui porte ce message, piloté par `EtatSynchro.desappairementNonPrevenu`.
 */
@Composable
fun EcranAppareil(
    reglages: Reglages,
    depot: Depot,
    surDesappairer: () -> Unit,
) {
    // Les médias réels du téléphone, chargés hors du fil principal — même
    // schéma que EcranSauvegarde/EcranDossiers. Ne sert qu'à ESTIMER ce que
    // la prochaine reprise devra relire.
    var medias by remember { mutableStateOf<List<Media>?>(null) }
    LaunchedEffect(Unit) {
        medias = withContext(Dispatchers.IO) { depot.lister() }
    }

    // Les candidats d'une reprise complète : les dossiers choisis, dans la
    // fenêtre de dates choisie — exactement ce qu'un nouvel appairage devra
    // reproposer, puisque l'horizon par dossier vit côté serveur, attaché à
    // l'appareil qu'on s'apprête à oublier.
    val candidats = remember(medias, reglages.debutJour, reglages.finJour,
                             reglages.dossiersSeuls, reglages.dossiersRecursifs) {
        medias?.let { liste ->
            val dossiersChoisis = Choix.dossiersASauvegarder(
                reglages, liste.map { it.dossier }.toSet())
            liste.filter { it.dossier in dossiersChoisis &&
                          Fenetre.dansLaFenetre(it, reglages.debutJour, reglages.finJour) }
        } ?: emptyList()
    }
    val nombreMedias = candidats.size
    val minutes = ceil(
        candidats.sumOf { it.taille } / OCTETS_PAR_SECONDE_SUPPOSES.toDouble() / 60.0
    ).toInt().coerceAtLeast(if (nombreMedias > 0) 1 else 0)

    var confirmationOuverte by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState())) {
        Text("Cet appareil", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(16.dp))
        Text("Désappairer coupe le lien avec le serveur actuel. Utilisez ce " +
             "geste pour vous dépanner ou changer de serveur — pas pour tout " +
             "reprendre : c'est la date de début, dans « Quand sauvegarder », " +
             "qui fait ce travail-là. Vos réglages (dossiers, dates) sont " +
             "conservés.")
        Spacer(Modifier.height(24.dp))
        OutlinedButton(onClick = { confirmationOuverte = true }) {
            Text("Désappairer ce téléphone")
        }
    }

    if (confirmationOuverte) {
        AlertDialog(
            onDismissRequest = { confirmationOuverte = false },
            title = { Text("Désappairer ce téléphone ?") },
            text = { Text("Vous devrez rescanner un QR. Le prochain appairage relira " +
                          "vos $nombreMedias médias (≈ $minutes min). Rien ne sera " +
                          "envoyé deux fois.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmationOuverte = false
                    surDesappairer()
                }) { Text("Désappairer") }
            },
            dismissButton = {
                TextButton(onClick = { confirmationOuverte = false }) { Text("Annuler") }
            })
    }
}
