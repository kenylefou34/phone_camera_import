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

/** Les deux comptes calculés pour l'écran, tenus séparés à dessein — voir
 *  [Fenetre.avantLaFenetre] et [Fenetre.apresLaFenetre]. */
private data class ComptesFenetre(val avant: Int, val apres: Int)

/**
 * Écran « Quand sauvegarder » : les deux bornes de la fenêtre, l'interrupteur
 * automatique, et ce que la fenêtre laisse dehors.
 *
 * Le compte « après la fin » est LA seule protection contre une borne de fin
 * oubliée (spec §4.2, ronde de correction 1/5 de la tâche 8) : il doit rester
 * visible sans action supplémentaire, jamais caché derrière un bouton ou un
 * onglet, et jamais noyé dans le compte, bien plus grand en pratique, des
 * médias simplement antérieurs à la date de début.
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
    // schéma que EcranDossiers. Ne sert qu'à COMPTER ; aucune coche n'est
    // modifiée ici.
    var medias by remember { mutableStateOf<List<Media>?>(null) }
    LaunchedEffect(Unit) {
        medias = withContext(Dispatchers.IO) { depot.lister() }
    }

    // Compté sur les dossiers CHOISIS seulement : un média d'un dossier non
    // suivi n'était de toute façon pas candidat à la sauvegarde, la fenêtre
    // n'y est pour rien — le compter donnerait un nombre qui accuse la
    // mauvaise cause. Recalculé à chaque changement de date ou d'automatique
    // (`reglages`), pas seulement au chargement : c'est ce qui rend les
    // compteurs vivants plutôt que figés au premier affichage.
    val comptes = remember(medias, reglages.debutJour, reglages.finJour,
                           reglages.dossiersSeuls, reglages.dossiersRecursifs) {
        medias?.let { liste ->
            val dossiersChoisis = Choix.dossiersASauvegarder(
                reglages, liste.map { it.dossier }.toSet())
            val candidats = liste.filter { it.dossier in dossiersChoisis }
            ComptesFenetre(
                avant = Fenetre.avantLaFenetre(candidats, reglages.debutJour),
                apres = Fenetre.apresLaFenetre(candidats, reglages.finJour))
        } ?: ComptesFenetre(0, 0)
    }
    val inversee = Fenetre.fenetreInversee(reglages.debutJour, reglages.finJour)

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
        if (inversee) {
            // Sans ce message, `Fenetre.dansLaFenetre` rend bien zéro média,
            // mais silencieusement : un grand compte « antérieur » ou
            // « postérieur » est indiscernable d'une fenêtre simplement
            // sévère. Remplace les deux comptes ci-dessous : les afficher en
            // même temps qu'une phrase disant « aucun média » serait
            // contradictoire, exactement ce que le point 3 de la ronde de
            // correction interdit (ne pas annoncer une chose et son
            // contraire).
            Text("Votre date de début est après votre date de fin : aucun " +
                 "média ne sera sauvegardé.",
                 color = MaterialTheme.colorScheme.error,
                 style = MaterialTheme.typography.bodyMedium)
        } else {
            if (comptes.avant > 0) {
                // Neutre, volontairement : un média antérieur à la date de
                // début est un choix assumé, pas une anomalie. Le texte ne
                // prétend pas savoir ce qui est déjà sur le serveur — une
                // question à laquelle répondre coûterait un aller-retour
                // réseau que ce compteur n'a pas à payer (point 3).
                Text("${comptes.avant} médias sont antérieurs à cette date. " +
                     "Ceux déjà sauvegardés le restent ; les autres ne seront " +
                     "pas repris tant que vous ne baissez pas la date de début.",
                     style = MaterialTheme.typography.bodyMedium)
            }
            if (comptes.apres > 0) {
                Spacer(Modifier.height(8.dp))
                // LE signal que cet écran existe pour rendre visible : une
                // date de fin oubliée bloque en silence toutes les photos à
                // venir. Couleur d'erreur et formulation distincte du compte
                // ci-dessus, pour qu'on ne les confonde jamais.
                Text("⚠️ ${comptes.apres} médias sont plus récents que votre " +
                     "date de fin et ne partiront pas tant qu'elle est posée.",
                     color = MaterialTheme.colorScheme.error,
                     style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/**
 * Une borne de la fenêtre : la valeur choisie, un bouton pour la changer, un
 * bouton pour l'effacer. Grisable par [active] sans jamais disparaître de
 * l'écran — étiquette et valeur comprises, pas seulement les boutons.
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
        // 0.38 est l'opacité standard du contenu désactivé en Material
        // Design — la même que celle que Material3 applique tout seul au
        // texte des boutons ci-dessous quand `enabled = false`. Sans elle,
        // seuls les boutons paraissaient inactifs : l'étiquette et la valeur
        // restaient en pleine opacité, contredisant visuellement le
        // grisage (point 4 de la ronde de correction).
        val couleur = LocalContentColor.current.copy(alpha = if (active) 1f else 0.38f)
        Column(Modifier.weight(1f)) {
            Text(etiquette, color = couleur, style = MaterialTheme.typography.labelMedium)
            Text(jour ?: "Non définie", color = couleur, style = MaterialTheme.typography.bodyLarge)
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
