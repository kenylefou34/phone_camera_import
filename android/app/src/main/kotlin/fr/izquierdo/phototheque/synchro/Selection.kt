package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media

object Selection {

    /**
     * Les médias à proposer au serveur, triés par date croissante.
     *
     * @param horizons       ce que renvoie /sync/horizon dans `dossiers`
     * @param depuisSecondes plancher pour un dossier absent de `horizons` ;
     *                       `null` signifie « aucune limite », pas « rien ».
     * @param plancherReprise ordre ponctuel d'aller rechercher du plus ancien.
     *   `null` en régime normal. Quand il vaut quelque chose, il ABAISSE le
     *   plancher de chaque dossier — il ne le remonte jamais, sinon reprendre
     *   « depuis 2020 » fermerait la fenêtre 2019-2020 d'un dossier dont
     *   l'horizon est à 2019.
     *
     *   C'est ce paramètre, et non une réécriture d'horizon côté serveur, qui
     *   fait qu'abaisser la date de début repropose les vieux médias. La
     *   monotonie (voir [Horizons.monotone]) garantit que le rattrapage ne
     *   fera pas redescendre l'horizon enregistré.
     *
     * La comparaison est `>=` et non `>` : l'horizon vaut la date d'un fichier
     * déjà envoyé, et deux médias peuvent porter exactement la même date quand
     * on retombe sur DATE_MODIFIED, qui n'a qu'une précision d'une seconde.
     * Avec `>`, le second serait écarté définitivement. Reproposer coûte un
     * aller-retour que l'anti-doublon du serveur tranche sans transfert ;
     * sauter coûte une photo.
     */
    fun candidats(
        medias: List<Media>,
        dossiersChoisis: Set<String>,
        horizons: Map<String, Double>,
        depuisSecondes: Double?,
        plancherReprise: Double? = null,
    ): List<Media> = medias
        .filter { it.dossier in dossiersChoisis }
        .filter { media ->
            val normal = horizons[media.dossier] ?: depuisSecondes
            val plancher = when {
                plancherReprise == null -> normal
                normal == null -> plancherReprise
                else -> minOf(normal, plancherReprise)
            }
            plancher == null || media.instant >= plancher
        }
        .sortedBy { it.instant }
}
