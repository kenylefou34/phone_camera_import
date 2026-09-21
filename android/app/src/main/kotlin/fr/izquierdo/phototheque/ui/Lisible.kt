package fr.izquierdo.phototheque.ui

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
}
