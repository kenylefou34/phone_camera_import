package fr.izquierdo.phototheque.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.medias.Media
import fr.izquierdo.phototheque.synchro.Choix
import fr.izquierdo.phototheque.synchro.Fenetre
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * Écran « Quand sauvegarder » : les deux bornes de la fenêtre, l'interrupteur
 * automatique, et le compte de médias que la fenêtre laisse dehors.
 *
 * Ce compte est LA seule protection contre une borne de fin oubliée (spec
 * §4.2) : il doit rester visible sans action supplémentaire, jamais caché
 * derrière un bouton ou un onglet.
 */
@Composable
fun EcranSauvegarde(
    reglages: Reglages,
    depot: Depot,
    surChangerDebut: (String?) -> Unit,
    surChangerFin: (String?) -> Unit,
    surChangerAuto: (Boolean) -> Unit,
) {
    // Les médias réels du téléphone, chargés hors du fil principal — même
    // schéma que EcranDossiers. Ne sert qu'à COMPTER le hors-fenêtre : aucune
    // coche n'est modifiée ici.
    var medias by remember { mutableStateOf<List<Media>?>(null) }
    LaunchedEffect(Unit) {
        medias = withContext(Dispatchers.IO) { depot.lister() }
    }

    // Compté sur les dossiers CHOISIS seulement : un média d'un dossier non
    // suivi n'était de toute façon pas candidat à la sauvegarde, la fenêtre
    // n'y est pour rien — le compter donnerait un nombre qui accuse la
    // mauvaise cause. Recalculé à chaque changement de date ou d'automatique
    // (`reglages`), pas seulement au chargement : c'est ce qui rend le
    // compteur vivant plutôt que figé au premier affichage.
    val horsFenetre = remember(medias, reglages.debutJour, reglages.finJour,
                               reglages.dossiersSeuls, reglages.dossiersRecursifs) {
        medias?.let { liste ->
            val dossiersChoisis = Choix.dossiersASauvegarder(
                reglages, liste.map { it.dossier }.toSet())
            val candidats = liste.filter { it.dossier in dossiersChoisis }
            Fenetre.horsFenetre(candidats, reglages.debutJour, reglages.finJour)
        } ?: 0
    }

    Column(Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState())) {
        Text("Quand sauvegarder", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(24.dp))

        SelecteurDate(
            etiquette = "Depuis",
            jour = reglages.debutJour,
            active = true,
            surChoix = surChangerDebut)
        Spacer(Modifier.height(12.dp))
        SelecteurDate(
            etiquette = "Jusqu'au",
            jour = reglages.finJour,
            // Grisée et VISIBLE, pas cachée : sans le champ sous les yeux, on
            // ne peut pas voir POURQUOI la date de fin a disparu (piège n°3
            // de la tâche — la borne oubliée doit rester repérable).
            active = !reglages.auto,
            surChoix = surChangerFin)

        Spacer(Modifier.height(16.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Switch(checked = reglages.auto, onCheckedChange = surChangerAuto)
            Spacer(Modifier.width(12.dp))
            Text("Sauvegarder automatiquement")
        }
        if (reglages.auto) {
            Spacer(Modifier.height(4.dp))
            // Le message qui accompagne le geste : `Reglages.enAuto()` efface
            // la date de fin, et l'écran doit le DIRE au moment où on coche —
            // sinon la disparition du champ ci-dessus serait inexpliquée.
            Text("La date de fin a été retirée : en automatique, la sauvegarde " +
                 "reprend depuis la dernière date et ne s'arrête plus.",
                 style = MaterialTheme.typography.bodySmall)
        }

        Spacer(Modifier.height(24.dp))
        if (horsFenetre > 0) {
            // En permanence dès que le compte est positif, et pas seulement
            // en cas de problème signalé ailleurs : c'est le seul garde-fou
            // contre une borne oubliée.
            Text("$horsFenetre média(s) sont hors de cette fenêtre et ne seront pas " +
                 "sauvegardés.", style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/**
 * Une borne de la fenêtre : la valeur choisie, un bouton pour la changer, un
 * bouton pour l'effacer. Grisable par [active] sans jamais disparaître de
 * l'écran.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SelecteurDate(
    etiquette: String,
    jour: String?,
    active: Boolean,
    surChoix: (String?) -> Unit,
) {
    var dialogueOuvert by remember { mutableStateOf(false) }

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(etiquette, style = MaterialTheme.typography.labelMedium)
            Text(jour ?: "Non définie", style = MaterialTheme.typography.bodyLarge)
        }
        TextButton(onClick = { dialogueOuvert = true }, enabled = active) {
            Text("Choisir")
        }
        if (jour != null) {
            TextButton(onClick = { surChoix(null) }, enabled = active) {
                Text("Effacer")
            }
        }
    }

    if (dialogueOuvert) {
        // Minuit UTC de la date en cours : c'est la convention documentée du
        // sélecteur Material3 pour `selectedDateMillis` — sans rapport avec
        // le choix d'ancrage de `Fenetre` (UTC+14 / UTC-12), qui ne concerne
        // que la comparaison aux instants réels des médias.
        val etat = rememberDatePickerState(
            initialSelectedDateMillis = jour?.let {
                LocalDate.parse(it).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
            })
        DatePickerDialog(
            onDismissRequest = { dialogueOuvert = false },
            confirmButton = {
                TextButton(onClick = {
                    etat.selectedDateMillis?.let {
                        surChoix(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate().toString())
                    }
                    dialogueOuvert = false
                }) { Text("OK") }
            },
            dismissButton = {
                TextButton(onClick = { dialogueOuvert = false }) { Text("Annuler") }
            },
        ) {
            DatePicker(state = etat)
        }
    }
}
