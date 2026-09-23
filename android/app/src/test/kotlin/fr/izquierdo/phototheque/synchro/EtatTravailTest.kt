package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Les quatre combinaisons des deux files. Le defaut que ces tests
 * interdisent : un `PeriodicWorkRequest` n'atteint JAMAIS d'etat terminal, il
 * reste `ENQUEUED` entre deux passes. Le compter comme une attente figeait
 * l'accueil sur « Sauvegarde en attente… » et grisait « Sauvegarder
 * maintenant » definitivement, des la seconde ou l'utilisateur cochait
 * l'interrupteur.
 */
class EtatTravailTest {

    /** Ce que WorkManager rend d'un travail periodique entre deux passes :
     *  pas termine, pas en cours. Il reste ainsi pour toujours. */
    private val periodiqueAuRepos = SuiviTravail(enCours = false, termine = false, tentatives = 0)

    @Test fun rien_nulle_part_donne_inactif() {
        assertEquals(EtatTravail.INACTIF, EtatTravail.combiner(emptyList(), emptyList()))
    }

    @Test fun l_automatique_programme_mais_au_repos_laisse_l_accueil_inactif() {
        // LE test de ce correctif : sans lui, « Sauvegarder maintenant » est
        // grise pour toujours et l'accueil annonce une attente qui n'existe
        // pas (spec §5.1 : « Synchroniser maintenant reste disponible a tout
        // moment »).
        assertEquals(EtatTravail.INACTIF,
                     EtatTravail.combiner(emptyList(), listOf(periodiqueAuRepos)))
    }

    @Test fun une_passe_automatique_qui_tourne_est_bien_annoncee() {
        // L'autre moitie : la file periodique doit quand meme donner EN_COURS,
        // sinon l'ecran dirait « rien en cours » pendant qu'une sauvegarde
        // automatique occupe le telephone.
        assertEquals(EtatTravail.EN_COURS, EtatTravail.combiner(
            emptyList(),
            listOf(SuiviTravail(enCours = true, termine = false, tentatives = 1))))
    }

    @Test fun une_passe_automatique_deja_tentee_ne_dit_pas_nouvelle_tentative() {
        // Meme raison que le repos : une passe periodique qui a deja tourne
        // une fois reste `ENQUEUED` avec un compteur non nul, pour toujours.
        // « Nouvelle tentative programmee… » serait alors affiche en
        // permanence, sur un telephone ou rien n'est en peine.
        assertEquals(EtatTravail.INACTIF, EtatTravail.combiner(
            emptyList(),
            listOf(SuiviTravail(enCours = false, termine = false, tentatives = 3))))
    }

    @Test fun la_file_manuelle_differee_donne_l_attente_de_reseau() {
        assertEquals(EtatTravail.EN_ATTENTE,
                     EtatTravail.combiner(listOf(periodiqueAuRepos), emptyList()))
    }

    @Test fun la_file_manuelle_deja_tentee_donne_une_nouvelle_tentative() {
        // Le cas le plus frequent est une permission retiree : « en attente
        // d'un reseau » contredirait le bandeau affiche juste au-dessus.
        assertEquals(EtatTravail.NOUVELLE_TENTATIVE, EtatTravail.combiner(
            listOf(SuiviTravail(enCours = false, termine = false, tentatives = 2)),
            emptyList()))
    }

    @Test fun la_file_manuelle_terminee_ne_laisse_rien_derriere_elle() {
        assertEquals(EtatTravail.INACTIF, EtatTravail.combiner(
            listOf(SuiviTravail(enCours = false, termine = true, tentatives = 1)),
            listOf(periodiqueAuRepos)))
    }

    @Test fun une_synchro_manuelle_qui_tourne_prime_sur_tout() {
        assertEquals(EtatTravail.EN_COURS, EtatTravail.combiner(
            listOf(SuiviTravail(enCours = true, termine = false, tentatives = 1)),
            listOf(periodiqueAuRepos)))
    }
}
