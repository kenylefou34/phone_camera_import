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

    /**
     * Vrai si [media] est strictement plus ancien que le début de la fenêtre.
     *
     * Partagé par [dansLaFenetre], [avantLaFenetre] et `Orchestrateur` pour
     * qu'ils ne puissent pas diverger : l'orchestrateur doit savoir si c'est
     * la borne BASSE, et non la haute, qui a écarté un média — les deux ne se
     * valent pas du tout du point de vue de l'horizon (voir son commentaire
     * sur les dossiers gelés).
     */
    fun avantLeDebut(media: Media, debut: String?): Boolean =
        debut != null && media.instant < debutDuJour(debut)

    /** Vrai si [media] est à ou après la fin (exclusive) de la fenêtre.
     *  Partagé par [dansLaFenetre] et [apresLaFenetre] pour qu'ils ne
     *  puissent pas diverger. */
    private fun apresFin(media: Media, fin: String?): Boolean =
        fin != null && media.instant >= finDuJour(fin)

    fun dansLaFenetre(media: Media, debut: String?, fin: String?): Boolean =
        !avantLeDebut(media, debut) && !apresFin(media, fin)

    /**
     * Les médias antérieurs au début de la fenêtre. Normal : ce sont les
     * vieux qu'on a choisi de ne pas reprendre.
     *
     * Ne JAMAIS le confondre avec [apresLaFenetre] à l'écran : mélanger les
     * deux dans un seul total noierait le seul signal qui compte (une date
     * de fin oubliée) sous le nombre, bien plus grand en pratique, des vieux
     * médias volontairement laissés de côté.
     */
    fun avantLaFenetre(medias: List<Media>, debut: String?): Int =
        medias.count { avantLeDebut(it, debut) }

    /**
     * Les médias POSTÉRIEURS à la fin de la fenêtre. C'est le compte qui
     * compte : une date de fin oubliée bloque en silence toutes les photos
     * à venir, et c'est le seul signal qui le révèle — noyé dans
     * [avantLaFenetre], il redeviendrait invisible.
     */
    fun apresLaFenetre(medias: List<Media>, fin: String?): Int =
        medias.count { apresFin(it, fin) }

    /**
     * Vrai si la date de début est postérieure à la date de fin :
     * l'utilisateur a interverti ses deux bornes.
     *
     * Détecte l'ERREUR de saisie, pas l'absence garantie de médias. À cause
     * des ancrages généreux de [debutDuJour]/[finDuJour] (UTC+14 / UTC-12,
     * 26 h d'écart), une inversion d'un seul jour laisse encore passer
     * quelques heures dans [dansLaFenetre] — une photo prise le 14 à 14 h à
     * Paris reste dans la fenêtre « 15 → 14 » (ronde de correction 2/5 de la
     * tâche 8 : le message affiché à l'écran ne doit donc JAMAIS promettre
     * « aucun média », seulement signaler l'erreur de saisie).
     *
     * Une seule borne posée n'est jamais inversée : il n'y a rien à
     * comparer. Une fenêtre d'un seul jour (`debut == fin`) non plus.
     */
    fun fenetreInversee(debut: String?, fin: String?): Boolean =
        debut != null && fin != null && LocalDate.parse(debut).isAfter(LocalDate.parse(fin))
}
