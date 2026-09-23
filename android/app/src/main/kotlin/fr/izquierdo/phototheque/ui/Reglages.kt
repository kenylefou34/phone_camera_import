package fr.izquierdo.phototheque.ui

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Ce que l'utilisateur a choisi : quoi sauvegarder, sur quelle période, et si
 * la sauvegarde se déclenche seule.
 *
 * Les dates sont des jours ISO (« 2026-09-15 ») et non des instants : une borne
 * saisie par un humain porte sur un jour entier, et stocker un instant ferait
 * dépendre le résultat du fuseau au moment de la saisie.
 *
 * [debutApplique] n'est pas un réglage mais une trace : il retient la valeur de
 * [debutJour] dont la reprise a déjà été menée à son terme. C'est lui qui fait
 * qu'abaisser la date de début repropose les vieux médias **une fois** et non
 * chaque nuit.
 */
@Serializable
data class Reglages(
    val dossiersSeuls: Set<String> = emptySet(),
    val dossiersRecursifs: Set<String> = emptySet(),
    val debutJour: String? = null,
    val finJour: String? = null,
    val debutApplique: String? = null,
    val auto: Boolean = false,
    /**
     * Les dossiers déjà VUS sur le téléphone à la dernière synchronisation.
     * Sert uniquement à signaler ceux qui sont apparus depuis : une coche
     * récursive est une délégation dans le temps, elle prendra demain des
     * dossiers qui n'existent pas aujourd'hui.
     */
    val dossiersConnus: Set<String> = emptySet(),
) {
    /**
     * Passage en automatique. Efface la date de fin, délibérément.
     *
     * Une borne haute oubliée bloquerait en silence toutes les photos à venir.
     * Le but déclaré de l'automatique étant de synchroniser depuis la dernière
     * date, la borne haute n'y a aucun sens : autant que le geste qui y mène
     * nettoie derrière lui. L'écran doit le DIRE au moment où on coche.
     */
    fun enAuto(): Reglages = copy(auto = true, finJour = null)

    /**
     * Vrai si la date de début a changé depuis la dernière reprise menée à
     * son terme. C'est ce qui fait qu'abaisser la date repropose les vieux
     * médias UNE FOIS et non chaque nuit.
     */
    fun repriseADemander(): Boolean = debutJour != null && debutJour != debutApplique

    fun versJson(): String = FORMAT.encodeToString(serializer(), this)

    companion object {
        /**
         * Ce qui était codé en dur au lot 1. Sert de valeur initiale pour que
         * la mise à jour de l'application ne change rien à ce qui est
         * sauvegardé tant que l'utilisateur n'a rien choisi.
         */
        val DEFAUT = Reglages(
            dossiersSeuls = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"))

        private val FORMAT = Json { ignoreUnknownKeys = true }

        /**
         * Relit des réglages, et survit à tout ce qui peut arriver au fichier.
         *
         * Préférences corrompues, rétrogradage de version, champ disparu : lever
         * ici depuis un initialiseur de ViewModel fermerait l'application à
         * CHAQUE lancement, définitivement. C'est exactement la panne que
         * `Coffre` a déjà rencontrée avec le Keystore.
         */
        fun depuisJson(json: String?): Reglages =
            if (json == null) DEFAUT
            else try { FORMAT.decodeFromString(serializer(), json) }
                 catch (e: Exception) { DEFAUT }
    }
}
