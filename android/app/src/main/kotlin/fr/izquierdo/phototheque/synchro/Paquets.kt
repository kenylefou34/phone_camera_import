package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media

/**
 * Découpe les candidats en lots bornés, chacun validé par son propre `commit`.
 *
 * Pourquoi : le 21/09/2026, une synchronisation de 971 fichiers et 14 Go a
 * demandé UN SEUL commit, qui a mis 1 h 02 à s'exécuter. Le téléphone avait
 * raccroché depuis longtemps, et si la synchro avait été interrompue avant,
 * les 14 Go auraient été perdus — rien n'était rangé, aucun horizon n'avait
 * bougé. Un paquet borne à la fois la perte possible et la durée d'un commit.
 */
object Paquets {

    /**
     * Point de départ, pas un résultat mesuré. Trop petit multiplie les tris
     * et les allers-retours ; trop grand rapproche du défaut qu'on corrige.
     * À réviser après le premier grand rattrapage.
     */
    const val TAILLE_MAX_OCTETS: Long = 500L * 1024 * 1024

    /**
     * @param medias déjà triés par date croissante — l'ordre est conservé tel
     *   quel, parce que c'est lui qui rend la règle de l'horizon juste.
     *
     * Un média plus gros que [tailleMax] fait son paquet à lui seul plutôt que
     * d'être refusé : une vidéo de 3 Go est un cas normal sur un téléphone, et
     * la sauter la perdrait.
     */
    fun decouper(
        medias: List<Media>,
        tailleMax: Long = TAILLE_MAX_OCTETS,
    ): List<List<Media>> {
        val paquets = mutableListOf<List<Media>>()
        var courant = mutableListOf<Media>()
        var cumul = 0L
        for (media in medias) {
            // Le test porte sur `courant.isNotEmpty()` AVANT tout : sans lui,
            // un media plus gros que la limite produirait un paquet vide puis
            // un paquet contenant ce media, et le paquet vide ferait un
            // commit inutile a chaque grosse video.
            if (courant.isNotEmpty() && cumul + media.taille > tailleMax) {
                paquets += courant
                courant = mutableListOf()
                cumul = 0L
            }
            courant += media
            cumul += media.taille
        }
        if (courant.isNotEmpty()) paquets += courant
        return paquets
    }
}
