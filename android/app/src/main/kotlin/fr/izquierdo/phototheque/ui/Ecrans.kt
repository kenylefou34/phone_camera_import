package fr.izquierdo.phototheque.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import fr.izquierdo.phototheque.synchro.Avancement
import fr.izquierdo.phototheque.synchro.Choix
import fr.izquierdo.phototheque.synchro.Phase

@Composable
fun EcranAccueil(etat: EtatSynchro, reglages: Reglages, maintenantMs: Long,
                 surSynchroniser: () -> Unit, surInterrompre: () -> Unit,
                 surVoirDetail: () -> Unit, surReglages: () -> Unit) {
    val jours = EtatSynchro.joursDepuis(maintenantMs, etat.derniereReussiteMs)
    // Le seuil descend à 3 jours quand l'automatique est actif : trois nuits
    // sans passe automatique sont déjà une anomalie, là où sept jours sans
    // geste volontaire n'ont rien d'étonnant.
    val alerte = jours == null || jours >= EtatSynchro.seuilAlerteJours(reglages.auto)

    Column(Modifier.fillMaxSize().padding(24.dp),
           horizontalAlignment = Alignment.CenterHorizontally,
           verticalArrangement = Arrangement.Center) {

        if (etat.permissionRefusee) Bandeau(
            "L'application n'a plus accès à vos photos. " +
            "Autorisez-la dans les réglages Android : sans cela, elle ne " +
            "sauvegarde plus rien.")
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
            if (it.interrompu) {
                // Neutre : un arret DEMANDE n'est pas une panne. Mais sans
                // cette ligne, l'ecran affichait « 0 envoyés · 0 refusés ·
                // 0 en échec », indiscernable d'une synchro qui n'avait
                // simplement rien a faire.
                Text("Sauvegarde interrompue.")
            }
            Text("${it.envoyes} envoyés · ${it.refuses} refusés · ${it.echecs} en échec")
        }
        // Quatrième panne, la seule qui n'avait pas encore de message : le
        // serveur a bien reçu les médias mais n'a pas su les ranger. Le compteur
        // de jours ne bouge pas — mais si la dernière réussite date du même
        // jour, l'accueil dirait « Sauvegardé aujourd'hui » pendant que le
        // rangement a échoué.
        val enErreur = (etat.dernierBilan?.bilanServeur?.get("errors") ?: 0.0).toInt()
        if (enErreur > 0) {
            Spacer(Modifier.height(8.dp))
            Text(
                // « Ils seront représentés » serait FAUX : le serveur détruit
                // le fichier qu'il n'a pas su ranger (app.py nettoie la
                // session avant de regarder `errors`). La seule chose vraie,
                // c'est que l'horizon n'a pas bougé — et pas seulement celui
                // du dossier fautif : l'orchestrateur gèle TOUS les dossiers
                // du paquet, puisque le serveur ne dit pas lequel a échoué.
                // « en entier » serait faux aussi : le dossier repart de son
                // horizon, pas de l'origine.
                "Le serveur n'a pas réussi à ranger $enErreur média(s). " +
                "Les dossiers concernés seront reproposés à la prochaine " +
                "sauvegarde : leur horizon n'a pas avancé.",
                color = MaterialTheme.colorScheme.error)
        }
        if (etat.serveurIntrouvable) {
            Spacer(Modifier.height(8.dp))
            // Formulation volontairement neutre : ce n'est pas une panne.
            Text("Serveur introuvable — vous n'êtes probablement pas chez vous.")
        }
        etat.erreur?.let {
            Spacer(Modifier.height(8.dp))
            // Une vraie panne, elle : dite en toutes lettres et en rouge, pour
            // ne surtout pas ressembler au message rassurant du dessus.
            Text("La sauvegarde a échoué : $it",
                 color = MaterialTheme.colorScheme.error)
        }

        Spacer(Modifier.height(24.dp))
        val enAttente = etat.enAttenteReseau || etat.nouvelleTentative
        Button(onClick = surSynchroniser, enabled = !etat.enCours) {
            Text(when {
                enAttente -> "Sauvegarde en attente…"
                etat.enCours -> "Sauvegarde en cours…"
                else -> "Sauvegarder maintenant"
            })
        }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = surReglages) { Text("Réglages") }
        // Cet écran reste le SEUL visible tant qu'aucun avancement n'a été
        // publié — MainActivity bascule sur EcranAvancement dès la première
        // publication. Et tant que le travail n'a pas démarré, rien ne tourne :
        // pas de service de premier plan, donc pas de notification, donc pas
        // d'autre bouton « Interrompre » que celui-ci. Sans ce bloc, un travail
        // que WorkManager diffère laisse un bouton grisé, aucune explication et
        // aucune sortie — indéfiniment.
        if (etat.enCours) {
            Spacer(Modifier.height(16.dp))
            LinearProgressIndicator()
            Spacer(Modifier.height(8.dp))
            // Trois cas, trois phrases. Les fondre en une seule en mentirait
            // deux fois : « en attente d'un réseau » est faux pendant la
            // recherche du serveur (3 à 13 s à chaque sauvegarde), et faux
            // pendant le délai de reprise qui suit une permission retirée —
            // où il contredirait en plus le bandeau affiché juste au-dessus.
            Text(when {
                etat.nouvelleTentative -> "Nouvelle tentative programmée…"
                etat.enAttenteReseau ->
                    "En attente d'un réseau… la sauvegarde démarrera toute seule."
                else -> "Recherche du serveur sur le réseau…"
            })
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = surInterrompre) { Text("Interrompre") }
        }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = surVoirDetail) { Text("Voir le détail") }
    }
}

/**
 * L'écran pendant une synchronisation — maquette B, « tout à l'écran ».
 *
 * L'accueil ne renvoie pas vers cet écran : il en DEVIENT un. Aucune
 * navigation à faire pour voir ce qui se passe.
 */
@Composable
fun EcranAvancement(avancement: Avancement, reglages: Reglages, surInterrompre: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
           horizontalAlignment = Alignment.CenterHorizontally) {

        Text(when (avancement.phase) {
                 Phase.ANALYSE -> "Analyse en cours"
                 Phase.ENVOI -> "Sauvegarde en cours"
                 Phase.RANGEMENT -> "Rangement sur le serveur"
             },
             style = MaterialTheme.typography.titleLarge)

        Spacer(Modifier.height(12.dp))
        Text("${avancement.fichiersFaits} / ${avancement.fichiersTotal}",
             style = MaterialTheme.typography.headlineMedium)
        Text("${Lisible.octets(avancement.octetsFaits)} sur " +
             Lisible.octets(avancement.octetsTotal),
             style = MaterialTheme.typography.bodyMedium)

        Spacer(Modifier.height(12.dp))
        // Barre DETERMINEE des qu'on connait le total : une barre qui tourne
        // sans fin pendant une heure ne dit rien.
        if (avancement.octetsTotal > 0L)
            LinearProgressIndicator(progress = { avancement.pourcentage / 100f },
                                    modifier = Modifier.fillMaxWidth())
        else LinearProgressIndicator(Modifier.fillMaxWidth())

        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(avancement.octetsParSeconde
                     ?.let { "${Lisible.octets(it.toLong())}/s" } ?: "—")
            Text(avancement.secondesRestantes?.let { Lisible.restant(it) } ?: "—")
        }

        avancement.mediaEnCours?.let { chemin ->
            Spacer(Modifier.height(20.dp))
            Text("Fichier en cours", style = MaterialTheme.typography.labelMedium)
            Text(chemin, style = MaterialTheme.typography.bodySmall)
            avancement.tailleEnCours?.let {
                Text(Lisible.octets(it), style = MaterialTheme.typography.bodySmall)
            }
            avancement.destinationPrevue?.let {
                Text("→ $it", style = MaterialTheme.typography.bodySmall)
            }
        }

        Spacer(Modifier.height(20.dp))
        Text("Paquet ${avancement.paquetCourant} · " +
             "${avancement.paquetsValides} validés",
             style = MaterialTheme.typography.labelMedium)

        // Repond a « je sais meme pas quel dossier ca synchronise », sans
        // avoir a ouvrir un autre ecran. Résolu depuis les réglages, pas une
        // constante : la synchro lit désormais les dossiers choisis par
        // l'utilisateur (Choix.dossiersASauvegarder), et un écran qui
        // afficherait encore les trois dossiers d'origine mentirait dès
        // qu'un seul réglage est changé.
        Spacer(Modifier.height(8.dp))
        val dossiersChoisis = Choix.dossiersASauvegarder(reglages, avancement.dossiersVus.keys)
        Text("Dossiers : " + dossiersChoisis.joinToString(", "),
             style = MaterialTheme.typography.bodySmall)
        // Pas de garde sur `dossiersVus.isNotEmpty()` ici : l'orchestrateur
        // calcule la carte avant la toute premiere publication, donc tout
        // `Avancement` recu a deja regarde MediaStore — y compris quand les
        // dossiers suivis sont absents, le cas le plus grave.
        //
        // `Choix.introuvables`, pas une simple différence d'ensembles : un
        // dossier coché en récursif n'apparaît JAMAIS lui-même dans
        // `dossiersVus` (MediaStore ne rend que les dossiers qui contiennent
        // directement des médias) — une différence brute crierait « Pictures
        // introuvable » alors que « Pictures/WhatsApp » est parfaitement
        // sauvegardé. Testé et pur dans `Choix`, pour ne pas dupliquer cette
        // règle dans deux écrans Compose, invérifiables.
        val absents = Choix.introuvables(reglages, avancement.dossiersVus.keys)
        if (absents.isNotEmpty()) {
            Text("Introuvables sur ce téléphone : ${absents.joinToString(", ")}",
                 color = MaterialTheme.colorScheme.error,
                 style = MaterialTheme.typography.bodySmall)
        }

        Spacer(Modifier.height(24.dp))
        OutlinedButton(onClick = surInterrompre) { Text("Interrompre") }
    }
}

@Composable
fun EcranAppairage(
    qrInvalide: Boolean,
    revoque: Boolean,
    desappairementNonPrevenu: Boolean,
    surScanner: () -> Unit,
) {
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
        // Suite d'un désappairage (écran « Cet appareil ») dont le serveur
        // n'a pas pu être prévenu — épinglage rompu, serveur réinstallé,
        // machine changée. L'effacement local, lui, a déjà eu lieu : ce
        // bandeau ne fait que dire ce qui reste à faire côté serveur.
        if (desappairementNonPrevenu) Bandeau(
            "Le serveur n'a pas pu être prévenu : l'appareil restera dans la " +
            "liste d'administration jusqu'à ce que vous l'y révoquiez.")
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
fun EcranDetail(etat: EtatSynchro, reglages: Reglages) {
    Column(Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState())) {
        Text("Dernière synchronisation", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(16.dp))
        val bilan = etat.dernierBilan
        if (bilan == null) {
            Text("Aucune synchronisation depuis le lancement.")
        } else {
            Text("Envoyés : ${bilan.envoyes}")
            Text("Refusés (extension non gérée) : ${bilan.refuses}")
            Text("En échec : ${bilan.echecs}")
            Spacer(Modifier.height(16.dp))
            Text("Bilan du serveur", style = MaterialTheme.typography.titleMedium)
            bilan.bilanServeur.forEach { (cle, valeur) -> Text("$cle : ${valeur.toInt()}") }
        }

        // Les dossiers sauvegardés sont ceux des RÉGLAGES, plus la constante
        // codée en dur d'origine (Reglages.DEFAUT en est la valeur de
        // départ). Si l'un d'eux n'existe pas sur ce téléphone — WhatsApp
        // récent range sous Android/media/com.whatsapp/… — la synchro réussit
        // avec ZÉRO média et rien ne le signale. Confronter les réglages à ce
        // que MediaStore contient vraiment est la seule façon de le voir.
        //
        // La section s'affiche dès qu'on a REGARDÉ (dossiersVus non null), même
        // si MediaStore n'a rien rendu : ce cas-là est le plus grave de tous, et
        // le masquer sous un test « la liste n'est pas vide » ferait disparaître
        // l'écran exactement quand il a quelque chose à dire.
        etat.dossiersVus?.let { vus ->
            Spacer(Modifier.height(24.dp))
            Text("Dossiers trouvés sur le téléphone",
                 style = MaterialTheme.typography.titleMedium)
            if (vus.isEmpty()) {
                Text("Aucun dossier trouvé — l'application ne voit aucun média.",
                     color = MaterialTheme.colorScheme.error)
            }
            // Résolu (Choix.resoudre), donc restreint à ce qui existe VRAIMENT
            // ici : un dossier récursif couvre des sous-dossiers qui ne sont
            // pas littéralement dans les réglages, et c'est justement ce que
            // « suivi » doit refléter pour chaque dossier réel.
            val dossiersChoisis = Choix.dossiersASauvegarder(reglages, vus.keys)
            vus.entries.sortedByDescending { it.value }.forEach { (nom, combien) ->
                val suivi = nom in dossiersChoisis
                Text("$nom : $combien" +
                     if (suivi) " — sauvegardé" else " — non sauvegardé")
            }
            // `Choix.introuvables`, pas une simple différence d'ensembles :
            // voir le commentaire identique dans `EcranAvancement` — un
            // dossier coché en récursif n'apparaît jamais lui-même dans
            // `vus.keys`, une différence brute crierait à tort.
            val absents = Choix.introuvables(reglages, vus.keys)
            if (absents.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text("Dossiers sauvegardés introuvables ici : ${absents.joinToString(", ")}",
                     color = MaterialTheme.colorScheme.error)
            }
        }

        // Les dossiers pris par une coche récursive depuis la dernière
        // synchronisation : une coche récursive est une délégation dans le
        // temps, elle prendra demain des dossiers qui n'existent pas
        // aujourd'hui (une application installée, un nouveau répertoire de
        // captures). Sans ce rappel, il faudrait surveiller soi-même.
        if (etat.dossiersNouveaux.isNotEmpty()) {
            Spacer(Modifier.height(24.dp))
            Text("Nouveaux dossiers pris par une coche « et ses sous-dossiers » :")
            etat.dossiersNouveaux.sorted().forEach { Text("• $it") }
        }
    }
}

/** Menu des réglages : trois portes, rien d'autre. */
@Composable
fun EcranReglages(surDossiers: () -> Unit, surSauvegarde: () -> Unit,
                  surAppareil: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp),
           verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Réglages", style = MaterialTheme.typography.headlineMedium)
        Button(onClick = surDossiers, modifier = Modifier.fillMaxWidth()) {
            Text("Dossiers à sauvegarder")
        }
        Button(onClick = surSauvegarde, modifier = Modifier.fillMaxWidth()) {
            Text("Quand sauvegarder")
        }
        Button(onClick = surAppareil, modifier = Modifier.fillMaxWidth()) {
            Text("Cet appareil")
        }
    }
}
