package fr.izquierdo.phototheque.synchro

/**
 * Ce que l'écran a besoin de savoir d'UNE exécution suivie par `WorkManager`.
 *
 * Trois valeurs, et pas un `WorkInfo` : celui-ci ne se construit pas
 * raisonnablement dans un test, et ce projet n'a aucun test d'instrumentation
 * Android. Réduire la décision à ces trois-là est ce qui la rend vérifiable
 * sur la JVM — même geste que [Reprise.fautIlRelancer] et
 * `Reglages.apresSynchro`.
 *
 * @param enCours l'exécution tourne en ce moment (`WorkInfo.State.RUNNING`).
 * @param termine elle a atteint un état final (`state.isFinished`) : réussie,
 *   échouée ou annulée. Une exécution **périodique** n'est JAMAIS terminée
 *   entre deux passes — c'est tout le piège que [EtatTravail.combiner] existe
 *   pour éviter.
 * @param tentatives `runAttemptCount` : 0 tant qu'aucune exécution n'a eu
 *   lieu. C'est le seul signal qui sépare « jamais démarré, on attend la
 *   contrainte » de « déjà tenté, on attend le délai de reprise ».
 */
data class SuiviTravail(
    val enCours: Boolean,
    val termine: Boolean,
    val tentatives: Int,
)

/**
 * Ce que `WorkManager` sait du travail de synchronisation.
 *
 * Les trois états actifs sont séparés parce que l'écran doit en dire trois
 * choses différentes, et qu'une seule phrase pour tous serait fausse deux fois
 * sur trois :
 * - EN_ATTENTE : rien ne tourne, la contrainte réseau n'est pas satisfaite ;
 * - NOUVELLE_TENTATIVE : rien ne tourne non plus, mais une exécution a DÉJÀ eu
 *   lieu et a demandé à être reprise. Dire « en attente d'un réseau » ici
 *   serait faux — le cas le plus fréquent est une permission retirée, dont le
 *   bandeau dit déjà, et correctement, qu'il faut aller dans les réglages ;
 * - EN_COURS : le travail s'exécute, mais tant qu'il n'a rien publié l'accueil
 *   reste le seul écran visible.
 */
enum class EtatTravail {
    INACTIF, EN_ATTENTE, NOUVELLE_TENTATIVE, EN_COURS;

    companion object {

        /**
         * L'état à afficher, à partir des deux files : la manuelle
         * (« Sauvegarder maintenant ») et l'automatique (la passe toutes
         * les 6 h).
         *
         * **La file périodique ne peut donner que EN_COURS**, et c'est LE
         * point de cette fonction. Un `PeriodicWorkRequest` n'atteint jamais
         * d'état terminal : entre deux passes il reste sagement `ENQUEUED`,
         * donc « pas terminé » y est vrai en permanence. Le compter comme une
         * attente, c'est figer l'accueil sur un mensonge dès que
         * l'utilisateur coche l'interrupteur — « Sauvegarde en attente… »,
         * une barre qui tourne, un bouton « Interrompre », et surtout
         * « Sauvegarder maintenant » GRISÉ pour toujours, alors que rien ne
         * tourne et que le WiFi est parfait. La spec §5.1 promet l'inverse :
         * « Synchroniser maintenant reste disponible à tout moment ».
         *
         * `RUNNING`, lui, vient bien des deux : une passe automatique qui
         * tourne doit s'annoncer, sinon l'écran dirait « rien en cours »
         * pendant qu'elle occupe le téléphone.
         */
        fun combiner(
            manuel: List<SuiviTravail>,
            automatique: List<SuiviTravail>,
        ): EtatTravail = when {
            manuel.any { it.enCours } || automatique.any { it.enCours } -> EN_COURS
            manuel.any { !it.termine && it.tentatives > 0 } -> NOUVELLE_TENTATIVE
            manuel.any { !it.termine } -> EN_ATTENTE
            else -> INACTIF
        }
    }
}
