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
     * Vrai si la date de début a **baissé** depuis la dernière reprise menée
     * à son terme. C'est ce qui fait qu'abaisser la date repropose les vieux
     * médias UNE FOIS et non chaque nuit.
     *
     * Seule une BAISSE est un ordre de reprise (spec §4.3 : « la baisser est
     * un ordre de reprise »). La remonter — de 2019 à 2024, pour réduire la
     * charge — ne doit surtout pas en déclencher une : une reprise repropose
     * et réempreinte (SHA-256 intégral) des dizaines de milliers de fichiers,
     * soit l'exact contraire du geste demandé.
     *
     * Les dates sont comparées comme des CHAÎNES, et c'est correct pour du
     * format ISO seul : même longueur, champs rangés du plus significatif au
     * moins significatif, chiffres complétés par des zéros — l'ordre
     * alphabétique y est l'ordre chronologique.
     *
     * Une date jamais appliquée (`debutApplique` nul) est toujours un ordre
     * de reprise : rien n'a encore été repris, il n'y a rien à comparer.
     */
    fun repriseADemander(): Boolean =
        debutJour != null && (debutApplique == null || debutJour < debutApplique)

    /**
     * Vrai si l'utilisateur n'a coché AUCUN dossier.
     *
     * Décocher les trois dossiers d'origine prend deux minutes sur l'écran
     * des dossiers. La synchronisation « réussit » alors à zéro média, le
     * compteur de l'accueil reste au vert, et plus rien n'est sauvegardé :
     * la panne muette canonique de ce projet. L'accueil doit le dire, et
     * [EtatSynchro.estUneReussite] refuser d'appeler ça une réussite.
     */
    fun aucunDossierChoisi(): Boolean =
        dossiersSeuls.isEmpty() && dossiersRecursifs.isEmpty()

    /**
     * Ce que ces réglages deviennent une fois une synchronisation menée à son
     * terme, réussie ou non. Extraite de `TravailSynchro` pour être testable
     * sur la JVM : c'est la seule pièce de ce `Worker` qui décide d'une
     * écriture DURABLE, et ce projet n'a aucun test d'instrumentation Android
     * pour la couvrir autrement (même geste que `Reprise.fautIlRelancer` et
     * `EtatSynchro.apresSynchro`).
     *
     * @param vus dossiers réellement vus sur le téléphone à cette
     *   synchronisation. Vide si rien n'a été vu — permission retirée, ou
     *   aucun des dossiers cochés n'existe sur ce téléphone.
     * @param reussiteComplete la synchronisation est allée à son terme SANS
     *   accroc : ni interrompue, ni révoquée, ni en échec local, ni en échec
     *   de rangement côté serveur. Un accès PARTIEL (Android 14+) doit déjà
     *   avoir été retiré de cette valeur par l'appelant : sinon `lister()` ne
     *   rendrait que les médias que l'utilisateur a sélectionnés, la reprise
     *   se croirait menée à son terme, et les médias hors sélection
     *   resteraient perdus sous l'horizon même après un accès complet
     *   accordé plus tard.
     * @param debutJourEnCours la date de début demandée pour CETTE
     *   synchronisation (`debutJour` au moment du lancement).
     *
     * `debutApplique` n'est rangé que si `vus` est ÉGALEMENT non vide : sans
     * cette garde, une synchronisation qui « réussit » sans avoir rien vu
     * (aucun des dossiers cochés n'existe sur ce téléphone) consommerait
     * quand même une reprise qui n'a jamais eu l'occasion de s'exécuter.
     * `dossiersConnus`, lui, ne dépend que de `vus` : il décrit ce qui EST
     * visible, pas ce que la synchronisation a accompli.
     */
    fun apresSynchro(
        vus: Set<String>,
        reussiteComplete: Boolean,
        debutJourEnCours: String?,
    ): Reglages = copy(
        dossiersConnus = if (vus.isNotEmpty()) vus else dossiersConnus,
        debutApplique = if (vus.isNotEmpty() && reussiteComplete) debutJourEnCours
                        else debutApplique,
    )

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
