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
    fun commit(session: String, horizons: Map<String, Double>): Map<String, Double>
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
        val etat = serveur.horizon()
        val depuis = etat.depuis?.let { jourVersSecondes(it) }
        val tous = source.lister()
        val dossiersChoisis = Choix.dossiersASauvegarder(
            reglages, tous.map { it.dossier }.toSet())
        // Un ordre PONCTUEL, pas un plancher permanent : `repriseADemander`
        // ne redevient vrai qu'après un nouveau changement de la date de
        // début (voir Reglages.repriseADemander).
        val plancherReprise =
            if (reglages.repriseADemander()) reglages.debutJour?.let { jourVersSecondes(it) }
            else null
        val candidats = Selection.candidats(
            tous, dossiersChoisis, etat.dossiers, depuis, plancherReprise)
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
        var arretes = emptySet<String>()
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
                // Arret immediat : le paquet en cours est jete. On previent au
                // mieux -- si l'appel echoue, les fichiers deja montes restent
                // sur le disque du NUC : le serveur ne purge aucune session
                // (issue #30), il n'y a pas de filet.
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
            val bilanPaquet = serveur.commit(reponse.session, aTransmettre)
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
        return Bilan(envoyes, refuses, echecs, revoque, bilanServeur, arrete)
    }

    /**
     * « 2026-09-01 » → secondes. Le champ `depuis` du contrat est une DATE ISO
     * nue, sans fuseau : il faut donc choisir a quel instant elle commence.
     *
     * On l'ancre a UTC+14, c'est-a-dire l'instant le plus PRECOCE auquel cette
     * date calendaire commence ou que ce soit sur Terre. Interpreter la date
     * dans le fuseau courant du telephone paraitrait plus naturel, mais un
     * changement de fuseau entre l'appairage et la synchro decalerait le
     * plancher — et vers l'ouest il reculerait trop tard, sautant en silence
     * des medias autour de la date d'appairage. Le sens choisi ici ne peut que
     * reproposer quelques heures de trop, que l'anti-doublon ecarte sans les
     * transferer.
     */
    private fun jourVersSecondes(jour: String): Double =
        java.time.LocalDate.parse(jour)
            .atStartOfDay(java.time.ZoneOffset.ofHours(14))
            .toEpochSecond().toDouble()
}
