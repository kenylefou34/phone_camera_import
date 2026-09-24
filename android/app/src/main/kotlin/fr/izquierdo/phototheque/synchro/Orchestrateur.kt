package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Empreintes
import fr.izquierdo.phototheque.medias.Media
import fr.izquierdo.phototheque.reseau.*
import fr.izquierdo.phototheque.ui.Reglages
import java.io.InputStream

interface SourceMedias {
    fun lister(): List<Media>
    fun ouvrir(media: Media): InputStream
}

/** Ce que l'orchestrateur attend du serveur. L'interface existe pour que
 *  l'orchestrateur soit testable sans réseau. */
interface Serveur {
    fun horizon(): ReponseHorizon
    fun plan(fichiers: List<FichierPlan>): ReponsePlan
    /** @param empreinteAttendue le SHA-256 deja calcule pour le plan : le
     *  serveur renvoie celui du fichier tel que recu, et les comparer est le
     *  seul moyen de reperer un transfert abime. */
    fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long,
                empreinteAttendue: String): ResultatEnvoi
    /** @param synchro identifiant partage par TOUS les paquets d'une meme
     *  synchronisation (issue #30) : c'est lui qui permet au serveur de
     *  regrouper N commits en une seule ligne d'historique.
     *  @param bilanApp cumul envoyes/refuses/echecs vu par l'application,
     *  depuis le debut de la synchronisation -- pas seulement du paquet en
     *  cours. */
    fun commit(session: String, horizons: Map<String, Double>,
              synchro: String, bilanApp: BilanApp): Map<String, Double>
    /** Oublie une session abandonnée. N'échoue jamais — voir ClientServeur. */
    fun abandonner(session: String)
}

data class Bilan(
    val envoyes: Int,
    val refuses: Int,
    val echecs: Int,
    val revoque: Boolean,
    val bilanServeur: Map<String, Double>,
    /**
     * La synchronisation s'est arrêtée avant la fin. Ce n'est PAS un échec :
     * ça ne doit ni déclencher d'alerte, ni provoquer de reprise automatique.
     *
     * L'orchestrateur ne sait pas QUI a demandé l'arrêt — le drapeau qu'on lui
     * passe vaut aussi bien pour un appui sur « Interrompre » que pour une
     * contrainte réseau perdue. C'est `TravailSynchro` qui fait la différence
     * avant de l'afficher : « Sauvegarde interrompue. » parle d'une décision.
     */
    val interrompu: Boolean = false,
    /**
     * Les dossiers dont l'horizon est gelé PAR LA DATE DE DÉBUT : sa borne
     * basse leur a écarté au moins un média, donc leur horizon n'avance pas
     * (voir `arretes` dans [Orchestrateur.synchroniser]).
     *
     * Issue #36 : ce gel protège la tranche écartée, mais il a un prix —
     * tout ce que ces dossiers ont dans la fenêtre est réempreinté à chaque
     * passe — et ce prix était muet. L'accueil l'annonce à partir d'ici.
     * Les gels dus à un échec n'y figurent PAS : ils se voient déjà dans les
     * compteurs d'échec, et les attribuer à la date ferait baisser une date
     * qui n'y est pour rien.
     */
    val gelesParLaDate: Set<String> = emptySet(),
)

/**
 * Enchaîne une synchronisation complète. C'est ici que se rencontrent le choix
 * des candidats (Selection) et la règle de l'horizon (Horizons) ; le reste du
 * module ne fait que les servir.
 */
class Orchestrateur(
    private val source: SourceMedias,
    private val serveur: Serveur,
    private val taillePaquet: Long = Paquets.TAILLE_MAX_OCTETS,
    private val horloge: () -> Long = System::currentTimeMillis,
    private val surAvancement: (Avancement) -> Unit = {},
) {
    fun synchroniser(
        reglages: Reglages,
        interrompu: () -> Boolean = { false },
    ): Bilan {
        // Engendre UNE FOIS par appel, jamais dans la boucle des paquets
        // plus bas : c'est ce meme identifiant, porte par chaque commit,
        // qui permet au serveur de regrouper les N paquets d'une seule
        // synchronisation en une seule ligne d'historique (issue #30). Le
        // remplacement des tirets donne 32 caracteres hexadecimaux,
        // compatible avec la forme que le serveur exige (_MOTIF_SYNCHRO).
        val synchroId = java.util.UUID.randomUUID().toString().replace("-", "")
        val etat = serveur.horizon()
        // La date de début choisie sur le téléphone prime sur la date de
        // depuis d'appairage du serveur : elle est le plancher PERMANENT des
        // dossiers sans horizon (spec §4.2 règle 2, ex. cocher un dossier
        // jamais synchronisé ne doit pas remonter à la nuit des temps), et un
        // réglage posé par l'utilisateur doit l'emporter sur une valeur
        // d'appairage qu'il ne voit jamais. Rôle DISTINCT de `plancherReprise`
        // plus bas, qui n'abaisse que ponctuellement.
        val depuis = (reglages.debutJour ?: etat.depuis)?.let { Fenetre.debutDuJour(it) }
        val tous = source.lister()
        val dossiersChoisis = Choix.dossiersASauvegarder(
            reglages, tous.map { it.dossier }.toSet())
        // Un ordre PONCTUEL, pas un plancher permanent : `repriseADemander`
        // ne redevient vrai qu'après un nouveau changement de la date de
        // début (voir Reglages.repriseADemander).
        val plancherReprise =
            if (reglages.repriseADemander()) reglages.debutJour?.let { Fenetre.debutDuJour(it) }
            else null
        val avantFenetre = Selection.candidats(
            tous, dossiersChoisis, etat.dossiers, depuis, plancherReprise)
        // La fenêtre choisie à l'écran (tâche 8) : un filtre EN PLUS du
        // plancher par horizon ci-dessus, pour un rattrapage CIBLÉ — elle
        // peut donc restreindre un dossier déjà connu, ce que le plancher
        // seul ne fait jamais (§4.1 de la spec : « une fenêtre, lancée à
        // la main »). Ce qu'elle écarte par le BAS impose un gel : voir
        // `arretes` plus bas.
        val candidats = avantFenetre.filter {
            Fenetre.dansLaFenetre(it, reglages.debutJour, reglages.finJour)
        }
        val lots = Paquets.decouper(candidats, taillePaquet)

        val octetsTotal = candidats.sumOf { it.taille }
        val dossiersVus = tous.groupingBy { it.dossier }.eachCount()
        val debit = Debit()
        debit.ajouter(0L, horloge())

        var envoyes = 0; var refuses = 0; var echecs = 0
        var revoque = false; var arrete = false
        var octetsFaits = 0L; var fichiersFaits = 0
        // L'ensemble des dossiers geles traverse TOUS les paquets. Le remettre
        // a zero a chaque paquet ferait avancer l'horizon par-dessus un
        // fichier en echec du paquet precedent : perte definitive.
        //
        // Il ne part PAS vide : un dossier dont la borne BASSE de la fenêtre
        // vient d'écarter un média est gelé d'entrée. Le piège, sinon —
        // l'horizon se poserait sur le dernier média ENVOYÉ, donc au-dessus de
        // la tranche que la fenêtre vient d'écarter, et le serveur ne
        // reproposerait plus jamais cette tranche-là, même une fois la date de
        // début redescendue. Des photos perdues sans qu'aucun compteur ne
        // bouge. C'est exactement le piège de `docs/CONTRAT-APP.md` §5.
        //
        // Le gel a un prix — l'horizon de ce dossier n'avance plus tant que la
        // fenêtre lui coupe quelque chose par le bas, donc tout est réempreinté
        // à chaque passe — et c'est le prix assumé : c'est lui qui garde la
        // tranche reproposable le jour où la date de début redescend,
        // exactement ce que l'écran « Quand sauvegarder » promet à
        // l'utilisateur (« ne seront pas repris tant que vous ne baissez pas
        // la date de début »).
        //
        // La borne HAUTE, elle, n'a besoin d'aucun filet : un horizon calculé
        // sur les seuls médias envoyés ne peut pas dépasser la date de fin.
        val gelesParLaDate: Set<String> = avantFenetre
            .filter { Fenetre.avantLeDebut(it, reglages.debutJour) }
            .mapTo(mutableSetOf()) { it.dossier }
        var arretes: Set<String> = gelesParLaDate
        var bilanServeur = emptyMap<String, Double>()
        var paquetsValides = 0

        fun publier(phase: Phase, media: Media? = null) {
            surAvancement(Avancement(
                phase = phase,
                fichiersFaits = fichiersFaits, fichiersTotal = candidats.size,
                octetsFaits = octetsFaits, octetsTotal = octetsTotal,
                octetsParSeconde = debit.octetsParSeconde(),
                secondesRestantes = debit.secondesRestantes(octetsTotal - octetsFaits),
                mediaEnCours = media?.chemin,
                tailleEnCours = media?.taille,
                destinationPrevue = media?.let {
                    Destination.dossier(it.instant, it.estVideo, it.chemin)
                },
                paquetCourant = paquetsValides + 1,
                paquetsValides = paquetsValides,
                dossiersVus = dossiersVus,
            ))
        }

        publier(Phase.ANALYSE)

        for (lot in lots) {
            // Revocation et interruption sont deux pannes DIFFERENTES pour
            // l'ecran (le fil du lot : cinq pannes, cinq messages distincts).
            // Les fondre en un seul `arrete` annoncerait "arret demande" pour
            // un appareil revoque — le pire message possible pour ce cas-la.
            if (revoque) break
            if (interrompu()) { arrete = true; break }

            // --- analyse : empreintes du paquet SEULEMENT ---
            val envois = mutableListOf<Envoi>()
            val empreintes = mutableMapOf<Media, String>()
            val lisibles = mutableListOf<Media>()
            for (media in lot) {
                publier(Phase.ANALYSE, media)
                try {
                    empreintes[media] = Empreintes.sha256(source.ouvrir(media))
                    lisibles += media
                } catch (e: Exception) {
                    // Ecarte du lot, mais INSCRIT comme echec : sans cette
                    // entree, Horizons.calculer ne le verrait pas, l'horizon
                    // sauterait par-dessus lui, et il serait perdu.
                    echecs++
                    envois += Envoi(media.dossier, media.instant, Issue.ECHEC)
                    // Un echec de LECTURE doit avancer la barre comme un
                    // echec d'ENVOI (plus bas) : un media supprime entre le
                    // listing et l'envoi est banal sur un telephone, pas une
                    // exception. Sans ca la barre resterait bloquee sous 100%.
                    fichiersFaits++; octetsFaits += media.taille
                }
            }

            val reponse = serveur.plan(lisibles.map {
                FichierPlan(it.chemin, it.taille, empreintes.getValue(it))
            })
            val reclamees = reponse.needed.toSet()

            // --- envoi ---
            var abandonne = false
            for (media in lisibles) {
                if (interrompu()) { abandonne = true; arrete = true; break }
                publier(Phase.ENVOI, media)
                val empreinte = empreintes.getValue(media)
                if (empreinte !in reclamees) {
                    envois += Envoi(media.dossier, media.instant, Issue.CONFIRME)
                    fichiersFaits++; octetsFaits += media.taille
                    debit.ajouter(octetsFaits, horloge())
                    continue
                }
                val issue = try {
                    when (serveur.envoyer(reponse.session, media.chemin,
                                          source.ouvrir(media), media.taille, empreinte)) {
                        ResultatEnvoi.OK -> { envoyes++; Issue.CONFIRME }
                        ResultatEnvoi.EXTENSION_REFUSEE -> { refuses++; Issue.IGNORE }
                        ResultatEnvoi.ECHEC -> { echecs++; Issue.ECHEC }
                        ResultatEnvoi.REVOQUE -> { revoque = true; null }
                    }
                } catch (e: Exception) {
                    echecs++
                    Issue.ECHEC
                }
                if (issue == null) break          // revoque : on arrete la boucle
                envois += Envoi(media.dossier, media.instant, issue)
                fichiersFaits++; octetsFaits += media.taille
                debit.ajouter(octetsFaits, horloge())
            }

            if (abandonne) {
                // Arret immediat : le paquet en cours est jete. On previent
                // le serveur au mieux (POST /sync/abandon) -- si l'appel
                // echoue (le reseau vient souvent d'etre la CAUSE meme de
                // l'abandon), la place n'est pas perdue pour autant : le
                // serveur purge de lui-meme toute session sans ecriture
                // depuis 24 h, au demarrage et apres chaque commit (issue
                // #30 ; cette purge-la n'a rien a voir avec POST
                // /sync/abandon). Appeler abandonner() ici sert quand meme a
                // liberer la place TOUT DE SUITE plutot que d'attendre ce
                // delai. Et on sort sans jamais valider cette session : le
                // serveur refuserait desormais son commit (410, session
                // retiree, docs/CONTRAT-APP.md §4.6).
                serveur.abandonner(reponse.session)
                break
            }

            // --- rangement ---
            publier(Phase.RANGEMENT)
            val resultat = Horizons.calculer(envois, arretes)
            arretes = resultat.arretes
            // Borne par ce que le serveur connaît déjà : un horizon ne doit
            // jamais reculer tout seul (Horizons.monotone). `etat.dossiers`,
            // lu une seule fois au DÉBUT de la synchronisation, suffit comme
            // `connus` uniquement parce que `Selection.candidats` trie tous
            // les candidats par instant croissant et que `Paquets.decouper`
            // conserve cet ordre (voir Paquets.kt:24-25) : un paquet plus
            // tardif ne peut donc jamais transmettre une date plus ancienne
            // qu'un paquet précédent du même dossier.
            val aTransmettre = Horizons.monotone(resultat.horizons, etat.dossiers)
            // Le bilan cote application est CUMULE depuis le debut de la
            // synchronisation (envoyes/refuses/echecs sont des compteurs de
            // fonction, pas remis a zero par paquet) : le dernier commit
            // porte donc le total de toute la synchro, pas du seul paquet
            // en cours -- exactement ce que le journal serveur attend pour
            // comparer ce que l'app croit avoir fait a ce qu'il a range.
            val bilanPaquet = serveur.commit(
                reponse.session, aTransmettre, synchroId, BilanApp(envoyes, refuses, echecs))
            // Le serveur n'ecrit AUCUN horizon quand son tri a echoue, et il a
            // DETRUIT le fichier fautif (app.py : le nettoyage de la session
            // s'execute avant le test sur `errors`). Si un paquet suivant
            // faisait avancer l'horizon de ces dossiers-la, le media detruit
            // passerait dessous et serait perdu pour toujours. Un seul commit
            // par synchro rendait cette protection inutile ; le decoupage en
            // paquets la rend indispensable. On gele donc TOUS les dossiers du
            // paquet, pas seulement ceux dont l'application a constate un
            // echec : de ceux-la, elle n'a rien vu du tout.
            if ((bilanPaquet["errors"] ?: 0.0) > 0.0) arretes = arretes + lot.map { it.dossier }
            // Cumule et non ecrase : avec N commits, ne garder que le dernier
            // ferait declarer reussie une synchro dont un paquet a echoue au
            // rangement (EtatSynchro.estUneReussite ne regarderait que celui-la).
            bilanServeur = (bilanServeur.keys + bilanPaquet.keys).associateWith {
                (bilanServeur[it] ?: 0.0) + (bilanPaquet[it] ?: 0.0)
            }
            paquetsValides++
        }

        publier(Phase.RANGEMENT)
        return Bilan(envoyes, refuses, echecs, revoque, bilanServeur, arrete, gelesParLaDate)
    }
}
