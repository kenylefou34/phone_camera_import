package fr.izquierdo.phototheque.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as itemsGrille
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.dp
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.medias.Media
import fr.izquierdo.phototheque.synchro.Arbre
import fr.izquierdo.phototheque.synchro.Choix
import fr.izquierdo.phototheque.synchro.Coche
import fr.izquierdo.phototheque.synchro.Noeud
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Choix des dossiers à sauvegarder.
 *
 * Une case par ligne : un appui déplie trois choix explicites. Deux autres
 * formes ont été maquettées puis écartées — deux cases par ligne (deux cibles
 * voisines au pouce se ratent) et une case plus un bouton « tout » (un clic de
 * moins, mais un vocabulaire à apprendre).
 */
@Composable
fun EcranDossiers(
    dossiersVus: Map<String, Int>?,
    reglages: Reglages,
    depot: Depot,
    surCoche: (String, Coche) -> Unit,
) {
    // L'arbre ne vient plus de la dernière synchro (`dossiersVus` peut être
    // `null` : au tout premier lancement, avant toute synchronisation, cet
    // écran — le cœur du lot 2 — serait sinon vide au moment exact où on
    // l'ouvre pour la première fois, un parcours pourtant banal : appairage,
    // puis Réglages → Dossiers). L'écran balaie lui-même MediaStore à
    // l'ouverture, hors du fil principal.
    //
    // `dossiersVus` sert de valeur de DÉPART quand elle existe déjà : ça évite
    // un écran vide le temps du balayage sur les ouvertures suivantes. Le
    // balayage frais la remplace ensuite silencieusement, sans indicateur
    // d'attente supplémentaire — seul le tout premier balayage (aucune valeur
    // de départ) en affiche un, plein écran.
    var racine by remember {
        mutableStateOf(dossiersVus?.let { Arbre.construire(it) })
    }
    LaunchedEffect(Unit) {
        val vus = withContext(Dispatchers.IO) {
            depot.lister().groupingBy { it.dossier }.eachCount()
        }
        racine = Arbre.construire(vus)
    }
    val arbre = racine
    if (arbre == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    // Le chemin où l'on se trouve : la navigation DANS l'arbre est un état
    // local à cet écran, distinct de la navigation entre écrans.
    var chemin by rememberSaveable { mutableStateOf(listOf<String>()) }
    var deplie by rememberSaveable { mutableStateOf<String?>(null) }
    // Le dossier dont l'aperçu est ouvert, ou null si aucun. État local et NON
    // sauvegardé : perdre un aperçu ouvert à une rotation d'écran est un
    // compromis raisonnable, ce n'est qu'une fenêtre de vérification.
    var apercu by remember { mutableStateOf<String?>(null) }

    val courants = chemin.fold(arbre) { niveau, libelle ->
        niveau.firstOrNull { it.libelle == libelle }?.enfants ?: emptyList()
    }

    Column(Modifier.fillMaxSize()) {
        // Fil d'Ariane : sans lui, on ne sait plus où l'on est passé six
        // niveaux plus bas.
        Text("📁 / " + chemin.joinToString(" / "),
             Modifier.padding(16.dp, 8.dp),
             style = MaterialTheme.typography.bodySmall)
        if (chemin.isNotEmpty()) {
            TextButton(onClick = { chemin = chemin.dropLast(1) }) { Text("← Remonter") }
        }
        LazyColumn(Modifier.weight(1f)) {
            items(courants, key = { it.chemin }) { noeud ->
                LigneDossier(
                    noeud = noeud,
                    coche = Choix.etat(noeud, reglages.dossiersSeuls,
                                       reglages.dossiersRecursifs),
                    heritageDe = Choix.parentRecursif(noeud.chemin, reglages.dossiersRecursifs),
                    // Les responsables d'une case à moitié pleine : sans eux,
                    // « Ne pas sauvegarder » décocherait toute la descendance
                    // sans que l'utilisateur sache ce qu'il décoche.
                    descendantsCoches = Choix.descendantsCoches(
                        noeud, reglages.dossiersSeuls, reglages.dossiersRecursifs),
                    deplie = deplie == noeud.chemin,
                    surDeplier = { deplie = if (deplie == noeud.chemin) null else noeud.chemin },
                    surChoix = { surCoche(noeud.chemin, it); deplie = null },
                    surEntrer = { chemin = chemin + noeud.libelle },
                    surApercu = { apercu = noeud.chemin })
            }
        }
    }

    // Cherché parmi les nœuds COURANTS : le bouton « voir » ne peut être
    // pressé que sur une ligne affichée, donc son nœud s'y trouve toujours au
    // moment de l'appui.
    courants.firstOrNull { it.chemin == apercu }?.let { noeud ->
        DialogueApercu(depot, noeud, surFermer = { apercu = null })
    }
}

@Composable
private fun LigneDossier(
    noeud: Noeud, coche: Coche, heritageDe: String?, descendantsCoches: List<String>,
    deplie: Boolean,
    surDeplier: () -> Unit, surChoix: (Coche) -> Unit,
    surEntrer: () -> Unit, surApercu: () -> Unit,
) {
    Column {
        Row(Modifier.fillMaxWidth().padding(16.dp, 10.dp),
            verticalAlignment = Alignment.CenterVertically) {
            TriCase(coche, surDeplier)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f).clickable(enabled = noeud.enfants.isNotEmpty()) { surEntrer() }) {
                Text(noeud.libelle, style = MaterialTheme.typography.bodyLarge)
                Text(sousTitre(noeud), style = MaterialTheme.typography.bodySmall)
            }
            // Sur `medias` (directs), pas `mediasTotal` : `Depot.apercu` ne
            // filtre QUE sur ce chemin exact, jamais sa descendance. Proposer
            // « voir » sur un dossier sans média direct ouvrirait une boîte
            // systématiquement vide, alors que le chevron permet justement d'y
            // descendre pour trouver les vrais médias.
            if (noeud.medias > 0) {
                TextButton(onClick = surApercu) { Text("voir") }
            }
            if (noeud.enfants.isNotEmpty()) {
                TextButton(onClick = surEntrer) { Text("›") }
            }
        }
        if (deplie) {
            Column(Modifier.padding(start = 52.dp, bottom = 8.dp)) {
                if (coche == Coche.HERITEE && heritageDe != null) {
                    // Pas de trois choix ici : « Ne pas sauvegarder » ne
                    // ferait RIEN (changerCoche retirerait ce chemin de deux
                    // ensembles où il n'est pas), et un choix qui ne fait rien
                    // est pire que pas de choix — l'utilisateur croirait
                    // avoir exclu ce dossier, alors qu'il continuerait de
                    // partir. On nomme le responsable et on dit quoi faire.
                    Text(
                        "Pris par « $heritageDe », coché avec ses sous-dossiers. " +
                        "Pour l'exclure, décochez « $heritageDe » et cochez ses " +
                        "sous-dossiers un par un.",
                        style = MaterialTheme.typography.bodySmall)
                } else {
                    // Case à moitié pleine : on nomme les responsables AVANT
                    // les trois choix. « Ne pas sauvegarder » va décocher
                    // toute la descendance — c'est la seule façon que ce
                    // choix fasse quelque chose ici (voir Choix.apresCoche) —
                    // et décocher sans dire quoi serait une surprise, y
                    // compris sur des dossiers qu'on ne voit pas depuis cette
                    // ligne.
                    if (coche == Coche.PARTIELLE && descendantsCoches.isNotEmpty()) {
                        Text("Sauvegardé par ses sous-dossiers : " +
                             Lisible.enumerer(descendantsCoches) +
                             ". « Ne pas sauvegarder » les décochera tous.",
                             style = MaterialTheme.typography.bodySmall)
                    }
                    // Les trois choix en clair. Le vocabulaire est la moitié
                    // de l'affaire : « récursivement » ne veut rien dire pour
                    // personne.
                    ChoixLigne("Ce dossier seulement", coche == Coche.DOSSIER) { surChoix(Coche.DOSSIER) }
                    ChoixLigne("Ce dossier et ses sous-dossiers", coche == Coche.RECURSIVE) { surChoix(Coche.RECURSIVE) }
                    ChoixLigne("Ne pas sauvegarder", coche == Coche.AUCUNE) { surChoix(Coche.AUCUNE) }
                }
            }
        }
    }
}

@Composable
private fun ChoixLigne(texte: String, actif: Boolean, surClic: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { surClic() }.padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = actif, onClick = surClic)
        Text(texte)
    }
}

@Composable
private fun TriCase(coche: Coche, surClic: () -> Unit) {
    // TriStateCheckbox et non Checkbox : l'état PARTIELLE doit se VOIR, sinon
    // on croit un dossier entièrement pris alors qu'il ne l'est qu'à moitié.
    TriStateCheckbox(
        state = when (coche) {
            Coche.AUCUNE -> androidx.compose.ui.state.ToggleableState.Off
            Coche.PARTIELLE -> androidx.compose.ui.state.ToggleableState.Indeterminate
            Coche.DOSSIER, Coche.RECURSIVE, Coche.HERITEE ->
                androidx.compose.ui.state.ToggleableState.On
        },
        onClick = surClic)
}

/**
 * Les chiffres qui parlent : c'est eux, et non des vignettes, qui font
 * reconnaître un dossier. Ils ne disent que des COMPTES — aucune taille n'est
 * calculée ici, et le bouton « voir » reste le moyen de démasquer un dossier
 * de vignettes.
 *
 * Les deux comptes sont donnés dès qu'ils diffèrent : `mediasTotal` seul, à
 * côté d'un choix « Ce dossier seulement » qui ne prendra que `medias`,
 * annoncerait un nombre que ce choix précis ne sauvegardera jamais.
 */
private fun sousTitre(noeud: Noeud): String = buildString {
    if (noeud.medias == noeud.mediasTotal) append("${noeud.medias} média(s)")
    else append("${noeud.medias} ici · ${noeud.mediasTotal} avec les sous-dossiers")
    if (noeud.enfants.isNotEmpty()) append(" · ${noeud.enfants.size} sous-dossier(s)")
}

/**
 * L'aperçu d'un dossier : ses premiers médias, en grille de quatre colonnes.
 *
 * Trois vignettes par ligne de l'arborescence ont été écartées : chaque ligne
 * visible déclencherait trois décodages d'image, avec cache et annulation au
 * défilement. Ici, un seul dossier est décodé à la fois, à la demande.
 *
 * `Depot.apercu` interroge MediaStore (une E/S) : chargé hors du fil
 * principal par `LaunchedEffect` + `Dispatchers.IO`, comme chaque vignette.
 */
@Composable
private fun DialogueApercu(depot: Depot, dossier: Noeud, surFermer: () -> Unit) {
    var medias by remember(dossier.chemin) { mutableStateOf<List<Media>?>(null) }
    LaunchedEffect(dossier.chemin) {
        medias = withContext(Dispatchers.IO) { depot.apercu(dossier.chemin) }
    }
    AlertDialog(
        onDismissRequest = surFermer,
        confirmButton = { TextButton(onClick = surFermer) { Text("Fermer") } },
        title = { Text(dossier.libelle) },
        text = {
            val liste = medias
            when {
                // En cours de chargement : une attente franche plutôt qu'un
                // écran figé, le temps que Depot.apercu revienne du fil d'E/S.
                liste == null -> Box(
                    Modifier.fillMaxWidth().height(96.dp),
                    contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                liste.isEmpty() -> Text("Aucun média dans ce dossier.")
                else -> Column {
                    LazyVerticalGrid(
                        columns = GridCells.Fixed(4),
                        modifier = Modifier.height(240.dp),
                    ) {
                        itemsGrille(liste, key = { it.chemin }) { media -> Vignette(depot, media) }
                    }
                    Spacer(Modifier.height(8.dp))
                    Text("${liste.size} premiers de ${dossier.medias}",
                         style = MaterialTheme.typography.bodySmall)
                }
            }
        })
}

/**
 * Une case de la grille d'aperçu.
 *
 * `null` n'est pas une anomalie : un fichier supprimé entre la requête
 * MediaStore et l'affichage est parfaitement ordinaire (`Depot.vignette`). La
 * case reste alors simplement vide — jamais de plantage, jamais de message
 * d'erreur pour un cas aussi banal.
 */
@Composable
private fun Vignette(depot: Depot, media: Media) {
    // Clé sur `chemin`, pas `id` : `chemin` identifie le média de façon
    // lisible et ne dépend pas de la numérotation interne de MediaStore.
    var bitmap by remember(media.chemin) { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(media.chemin) {
        bitmap = withContext(Dispatchers.IO) { depot.vignette(media) }
    }
    Box(Modifier.aspectRatio(1f).padding(2.dp)) {
        bitmap?.let {
            Image(it.asImageBitmap(), contentDescription = media.nom,
                  modifier = Modifier.fillMaxSize())
        }
    }
}
