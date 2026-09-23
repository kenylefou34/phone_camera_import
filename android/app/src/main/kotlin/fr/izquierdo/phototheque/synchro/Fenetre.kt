package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * La fenêtre de dates choisie par l'utilisateur.
 *
 * Les bornes sont des jours ISO, pas des instants : une date saisie par un
 * humain porte sur un jour entier.
 *
 * **Chaque borne est élargie dans SON sens**, et c'est délibéré. Le téléphone
 * ne sait pas dans quel fuseau une photo a été prise : `instant` est un
 * horodatage absolu, et « le 15 septembre » ne désigne pas le même intervalle
 * à Paris, à Tokyo et à Los Angeles. Une borne trop étroite écarterait des
 * médias en silence — une borne trop large en repropose quelques heures de
 * trop, que l'anti-doublon du serveur écarte sans les transférer. Le choix
 * est donc toujours le même : **reproposer plutôt que sauter.**
 */
object Fenetre {

    /**
     * Le tout premier instant qui peut appartenir à ce jour, où que ce soit :
     * minuit au fuseau le plus en avance (UTC+14).
     *
     * Même raisonnement, et même valeur, que la fonction qu'`Orchestrateur`
     * utilisait pour l'horizon : vers l'est, la borne ne peut qu'être trop
     * généreuse ; vers l'ouest, elle sauterait des médias.
     */
    fun debutDuJour(jour: String): Double =
        LocalDate.parse(jour).atStartOfDay(ZoneOffset.ofHours(14)).toEpochSecond().toDouble()

    /**
     * Le premier instant qui n'appartient PLUS à ce jour, où que ce soit :
     * minuit du lendemain au fuseau le plus en retard (UTC-12). Borne
     * **exclusive**.
     *
     * Réutiliser [debutDuJour] en y ajoutant 24 h serait le piège : la
     * fenêtre s'arrêterait à midi UTC le jour choisi, c'est-à-dire **vers
     * 14 h à Paris**. Toutes les photos de l'après-midi et de la soirée du
     * dernier jour disparaîtraient, sans un mot.
     */
    fun finDuJour(jour: String): Double =
        LocalDate.parse(jour).plusDays(1)
            .atStartOfDay(ZoneOffset.ofHours(-12)).toEpochSecond().toDouble()

    fun dansLaFenetre(media: Media, debut: String?, fin: String?): Boolean {
        if (debut != null && media.instant < debutDuJour(debut)) return false
        if (fin != null && media.instant >= finDuJour(fin)) return false
        return true
    }

    /**
     * Combien de médias la fenêtre laisse dehors.
     *
     * Ce nombre doit être affiché EN PERMANENCE. Une fenêtre est un filtre, et
     * un filtre muet est une panne silencieuse : c'est exactement le piège de
     * la date de fin oubliée.
     */
    fun horsFenetre(medias: List<Media>, debut: String?, fin: String?): Int =
        medias.count { !dansLaFenetre(it, debut, fin) }
}
