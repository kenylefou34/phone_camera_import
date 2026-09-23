package fr.izquierdo.phototheque.synchro

/** Ce qu'est devenu un envoi. */
enum class Issue {
    /** Le serveur a répondu 200 : le média est chez lui. */
    CONFIRME,

    /** Refusé (400, extension non prise en charge). Volontairement PAS un
     *  échec : bloquer l'horizon dessus fermerait le dossier à jamais. */
    IGNORE,

    /** Tout le reste : réseau coupé, 5xx, erreur de lecture locale. */
    ECHEC,
}

/** Un envoi tenté, avec la date du média concerné (secondes). */
data class Envoi(val dossier: String, val instant: Double, val issue: Issue)

/**
 * Ce que rend [Horizons.calculer] : les horizons à transmettre, et la liste
 * des dossiers dont l'horizon est GELÉ pour le reste de la synchronisation.
 */
data class ResultatHorizons(
    val horizons: Map<String, Double>,
    val arretes: Set<String>,
)

object Horizons {

    /**
     * Horizon à transmettre pour chaque dossier : la date du dernier fichier
     * confirmé AVANT le premier échec de ce dossier.
     *
     * Pourquoi pas « la date la plus haute confirmée » : si le fichier n° 5
     * échoue et que le n° 6 réussit, retenir la plus haute ferait sauter
     * l'horizon par-dessus le n° 5, qui ne serait PLUS JAMAIS proposé par le
     * serveur — perte définitive et silencieuse.
     *
     * @param dejaArretes les dossiers gelés par les PAQUETS PRÉCÉDENTS de la
     *   même synchronisation. Sans ce paramètre, le découpage en paquets
     *   rouvrirait exactement le trou que cette fonction existe pour combler :
     *   un dossier en échec au paquet 12 verrait son horizon avancer au
     *   paquet 13, et le fichier fautif serait perdu. L'appelant repasse
     *   [ResultatHorizons.arretes] d'un paquet au suivant.
     *
     * La fonction reste pure : aucun état retenu entre deux appels.
     */
    fun calculer(
        envois: List<Envoi>,
        dejaArretes: Set<String> = emptySet(),
    ): ResultatHorizons {
        val horizons = mutableMapOf<String, Double>()
        val arretes = dejaArretes.toMutableSet()
        // Tri par date, puis ECHEC d'abord A DATE EGALE. Deux envois du meme
        // dossier peuvent porter exactement la meme date : DATE_MODIFIED n'a
        // qu'une precision d'une seconde et une rafale en produit plusieurs.
        // Sans ce second critere, `sortedBy` etant un tri STABLE, le resultat
        // dependrait de l'ordre de la liste d'entree. A egalite on retient le
        // cas prudent : l'echec arrete le dossier, quitte a reproposer
        // quelques fichiers que l'anti-doublon ecartera sans les transferer.
        for (envoi in envois.sortedWith(
            compareBy({ it.instant }, { if (it.issue == Issue.ECHEC) 0 else 1 })
        )) {
            if (envoi.dossier in arretes) continue
            when (envoi.issue) {
                Issue.ECHEC -> arretes += envoi.dossier
                Issue.CONFIRME, Issue.IGNORE -> horizons[envoi.dossier] = envoi.instant
            }
        }
        return ResultatHorizons(horizons, arretes)
    }

    /**
     * Les horizons à transmettre, bornés par ceux que le serveur connaît déjà.
     *
     * L'horizon signifie « tout ce qui est plus récent que cette date a été
     * proposé ». Reproposer du plus ancien ne le rend pas faux : il ne doit donc
     * JAMAIS reculer tout seul.
     *
     * Sans cette borne, une fenêtre de rattrapage 2019-2020 posée sur un téléphone
     * déjà synchronisé jusqu'en septembre 2026 ferait écrire « fin 2020 » au
     * serveur — `set_horizon` (`phototheque/devices.py:189`) écrit tel quel ce
     * qu'on lui envoie, et la boucle de commit ne borne que par le haut. La
     * mémoire de 2026 serait effacée et six ans de médias reproposés chaque nuit.
     *
     * Seuls les dossiers présents dans [nouveaux] ressortent : transmettre les
     * autres ferait écrire au serveur des horizons qu'aucun envoi ne justifie.
     */
    fun monotone(
        nouveaux: Map<String, Double>,
        connus: Map<String, Double>,
    ): Map<String, Double> =
        nouveaux.mapValues { (dossier, valeur) -> maxOf(valeur, connus[dossier] ?: valeur) }
}
