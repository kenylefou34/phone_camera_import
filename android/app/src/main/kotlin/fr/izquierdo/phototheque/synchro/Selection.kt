package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media

object Selection {

    /**
     * Les médias à proposer au serveur, triés par date croissante.
     *
     * @param horizons       ce que renvoie /sync/horizon dans `dossiers`
     * @param depuisSecondes plancher pour un dossier absent de `horizons` ;
     *                       `null` signifie « aucune limite », pas « rien ».
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
    ): List<Media> = medias
        .filter { it.dossier in dossiersChoisis }
        .filter { media ->
            val plancher = horizons[media.dossier] ?: depuisSecondes
            plancher == null || media.instant >= plancher
        }
        .sortedBy { it.instant }
}
