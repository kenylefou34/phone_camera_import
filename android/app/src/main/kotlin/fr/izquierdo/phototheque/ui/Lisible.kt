package fr.izquierdo.phototheque.ui

import fr.izquierdo.phototheque.synchro.Coche

/**
 * Mise en forme des nombres pour l'écran. Séparée des composables pour être
 * testable sur la JVM : un « ~ Infinity min » affiché en production ne se
 * rattrape pas.
 */
object Lisible {

    fun octets(n: Long): String {
        if (n < 1024) return "$n o"
        var x = n.toDouble()
        for (unite in listOf("Ko", "Mo", "Go", "To")) {
            x /= 1024.0
            if (x < 1024.0) return String.format("%.1f %s", x, unite).replace('.', ',')
        }
        return String.format("%.1f Po", x).replace('.', ',')
    }

    fun duree(secondes: Long): String = when {
        secondes < 60 -> if (secondes <= 0) "moins d'une minute" else "$secondes s"
        secondes < 3600 -> "${secondes / 60} min"
        else -> String.format("%d h %02d", secondes / 3600, (secondes % 3600) / 60)
    }

    /**
     * Le temps restant tel que l'écran l'affiche.
     *
     * Le tilde marque une estimation, mais « ~ moins d'une minute » se lit
     * comme une faute de frappe. La règle vit ici et pas dans le composable :
     * le seuil qui produit ce texte est celui de [duree], les séparer les
     * ferait diverger au premier changement.
     */
    fun restant(secondes: Long): String =
        if (secondes <= 0) duree(secondes) else "~ ${duree(secondes)}"

    /**
     * Une liste de noms, tronquée pour tenir dans une phrase.
     *
     * Un dossier peut avoir trente sous-dossiers cochés : les nommer tous
     * ferait un pavé que personne ne lit, et n'en nommer aucun ferait un
     * geste aveugle. Le compte du reste est donné, jamais escamoté.
     *
     * Ici plutôt que dans le composable : le calcul du reste est un
     * « à un près » typique, et rien ne vérifie un composable dans ce projet.
     */
    /**
     * Ce qu'on dit, au-dessus des trois choix d'un dossier, des sous-dossiers
     * que « Ne pas sauvegarder » va décocher avec lui ; `null` s'il n'y en a
     * aucun.
     *
     * `coche` est volontairement IGNORÉ (issue #38) : `Choix.apresCoche`
     * décoche toute la descendance quel que soit l'état de départ. Réserver
     * le message à la case à moitié pleine laissait un dossier coché « seul »
     * ou « avec ses sous-dossiers » perdre en silence les coches posées une à
     * une sur ses enfants. Le paramètre reste pour que l'appelant n'ait pas à
     * se demander si l'état compte : il ne compte pas.
     */
    @Suppress("UNUSED_PARAMETER")
    fun avertissementDecoche(coche: Coche, descendantsCoches: List<String>): String? =
        if (descendantsCoches.isEmpty()) null
        else "Sauvegardé par ses sous-dossiers : " + enumerer(descendantsCoches) +
            ". « Ne pas sauvegarder » les décochera tous."

    /**
     * Ce qu'on dit sur l'accueil des dossiers dont la date de début gèle
     * l'horizon (`Bilan.gelesParLaDate`) ; `null` s'il n'y en a aucun.
     *
     * Issue #36 : ce gel protège les médias que la date écarte, mais oblige à
     * réexaminer (réempreinter) tout le reste du dossier à chaque passe. Sans
     * cette phrase, rien ne le disait : seul l'allongement des sauvegardes le
     * trahissait. On dit le fait, son coût, et le geste qui le lève.
     */
    fun gelParLaDate(dossiers: Set<String>): String? =
        if (dossiers.isEmpty()) null
        else "Votre date de début retient ${dossiers.size} dossier(s) : " +
            enumerer(dossiers.sorted()) + ". Leurs médias plus anciens sont gardés " +
            "pour plus tard, mais tout ce qu'ils contiennent dans la fenêtre est " +
            "réexaminé à chaque sauvegarde. Baissez ou effacez la date de début " +
            "pour lever cette attente."

    fun enumerer(noms: List<String>, maximum: Int = 3): String {
        val montres = noms.take(maximum)
        val reste = noms.size - montres.size
        return montres.joinToString(", ") + if (reste > 0) " et $reste autre(s)" else ""
    }
}
