package fr.izquierdo.phototheque.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import fr.izquierdo.phototheque.synchro.Desappairage

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
 *
 * La conséquence annoncée dans la confirmation ci-dessous vient de
 * `Desappairage.consequenceReappairage`, pas d'un calcul fait ici : ce que
 * relira le prochain appairage dépend de `reglages.debutJour`, pas d'un
 * compte de médias locaux — voir la doc de cette fonction pour la raison
 * (l'horizon posé par le serveur à CHAQUE appairage, et ce qui prime dessus).
 */
@Composable
fun EcranAppareil(
    reglages: Reglages,
    surDesappairer: () -> Unit,
) {
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
            text = { Text("Vous devrez rescanner un QR. " +
                          Desappairage.consequenceReappairage(reglages.debutJour)) },
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
