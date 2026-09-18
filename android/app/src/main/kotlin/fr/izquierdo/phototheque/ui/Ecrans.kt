package fr.izquierdo.phototheque.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun EcranAccueil(etat: EtatSynchro, maintenantMs: Long,
                 surSynchroniser: () -> Unit, surVoirDetail: () -> Unit) {
    val jours = EtatSynchro.joursDepuis(maintenantMs, etat.derniereReussiteMs)
    val alerte = jours == null || jours >= EtatSynchro.SEUIL_ALERTE_JOURS

    Column(Modifier.fillMaxSize().padding(24.dp),
           horizontalAlignment = Alignment.CenterHorizontally,
           verticalArrangement = Arrangement.Center) {

        if (etat.accesPartiel) Bandeau(
            "L'application ne voit qu'une partie de vos photos. " +
            "Autorisez l'accès à toutes les photos dans les réglages Android.")
        if (etat.revoque) Bandeau(
            "Cet appareil a été révoqué. Scannez un nouveau QR sur la page du serveur.")

        Text(
            text = when {
                jours == null -> "Jamais sauvegardé"
                jours == 0L -> "Sauvegardé aujourd'hui"
                jours == 1L -> "Sauvegardé hier"
                else -> "Dernière sauvegarde réussie il y a $jours jours"
            },
            style = MaterialTheme.typography.headlineSmall,
            color = if (alerte) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.onSurface,
        )

        etat.dernierBilan?.let {
            Spacer(Modifier.height(8.dp))
            Text("${it.envoyes} envoyés · ${it.refuses} refusés · ${it.echecs} en échec")
        }
        if (etat.serveurIntrouvable) {
            Spacer(Modifier.height(8.dp))
            // Formulation volontairement neutre : ce n'est pas une panne.
            Text("Serveur introuvable — vous n'êtes probablement pas chez vous.")
        }

        Spacer(Modifier.height(24.dp))
        Button(onClick = surSynchroniser, enabled = !etat.enCours) {
            Text(if (etat.enCours) "Sauvegarde en cours…" else "Sauvegarder maintenant")
        }
        if (etat.enCours) { Spacer(Modifier.height(16.dp)); LinearProgressIndicator() }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = surVoirDetail) { Text("Voir le détail") }
    }
}

@Composable
fun EcranAppairage(qrInvalide: Boolean, revoque: Boolean, surScanner: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp),
           horizontalAlignment = Alignment.CenterHorizontally,
           verticalArrangement = Arrangement.Center) {
        Text("Photothèque", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(16.dp))
        Text("Ouvrez la page d'appairage du serveur sur un ordinateur, " +
             "puis scannez le QR affiché.")
        if (revoque) Bandeau(
            "Cet appareil a été révoqué. Scannez un nouveau QR pour le réautoriser.")
        if (qrInvalide) Bandeau(
            "Ce n'est pas un QR de photothèque. Vérifiez que vous scannez bien " +
            "celui de la page d'appairage du serveur.")
        Spacer(Modifier.height(24.dp))
        Button(onClick = surScanner) { Text("Scanner le QR") }
    }
}

@Composable
private fun Bandeau(texte: String) {
    Card(Modifier.fillMaxWidth().padding(bottom = 16.dp),
         colors = CardDefaults.cardColors(
             containerColor = MaterialTheme.colorScheme.errorContainer)) {
        Text(texte, Modifier.padding(16.dp))
    }
}

@Composable
fun EcranDetail(etat: EtatSynchro) {
    Column(Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState())) {
        Text("Dernière synchronisation", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(16.dp))
        val bilan = etat.dernierBilan
        if (bilan == null) { Text("Aucune synchronisation depuis le lancement.") ; return@Column }
        Text("Envoyés : ${bilan.envoyes}")
        Text("Refusés (extension non gérée) : ${bilan.refuses}")
        Text("En échec : ${bilan.echecs}")
        Spacer(Modifier.height(16.dp))
        Text("Bilan du serveur", style = MaterialTheme.typography.titleMedium)
        bilan.bilanServeur.forEach { (cle, valeur) -> Text("$cle : ${valeur.toInt()}") }
    }
}
