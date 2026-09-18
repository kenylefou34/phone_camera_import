package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import fr.izquierdo.phototheque.reseau.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.InputStream

class OrchestrateurTest {

    private fun media(instant: Double, nom: String = "a.jpg") =
        Media(instant.toLong(), "DCIM/Camera", nom, 10L, instant)

    /** Serveur simule : on programme le resultat de chaque envoi. */
    private class FauxServeur(
        val horizons: Map<String, Double> = emptyMap(),
        val reclame: (List<FichierPlan>) -> List<String> = { f -> f.map { it.hash } },
        val resultats: MutableList<ResultatEnvoi> = mutableListOf(),
    ) : Serveur {
        var horizonsEnvoyes: Map<String, Double>? = null
        var commitAppele = false
        override fun horizon() = ReponseHorizon(null, horizons)
        override fun plan(f: List<FichierPlan>) = ReponsePlan("a".repeat(32), reclame(f))
        override fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long) =
            if (resultats.isEmpty()) ResultatEnvoi.OK else resultats.removeAt(0)
        override fun commit(session: String, horizons: Map<String, Double>): Map<String, Double> {
            horizonsEnvoyes = horizons; commitAppele = true; return mapOf("sorted" to 1.0)
        }
    }

    private class FausseSource(val medias: List<Media>) : SourceMedias {
        override fun lister() = medias
        override fun ouvrir(media: Media): InputStream = "contenu".byteInputStream()
    }

    @Test fun cas_nominal_tout_est_envoye_et_l_horizon_avance() {
        val serveur = FauxServeur()
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0), media(200.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(2, bilan.envoyes)
        assertEquals(mapOf("DCIM/Camera" to 200.0), serveur.horizonsEnvoyes)
    }

    @Test fun un_echec_au_milieu_arrete_l_horizon_avant_lui() {
        val serveur = FauxServeur(resultats = mutableListOf(
            ResultatEnvoi.OK, ResultatEnvoi.ECHEC, ResultatEnvoi.OK))
        val bilan = Orchestrateur(
            FausseSource(listOf(media(100.0), media(200.0), media(300.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
        assertEquals(1, bilan.echecs)
    }

    @Test fun le_commit_est_appele_MEME_apres_un_echec() {
        // Sans cela les fichiers deja recus resteraient indefiniment dans le
        // depot temporaire du NUC, sans que rien ne les range.
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.ECHEC))
        Orchestrateur(FausseSource(listOf(media(100.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertTrue(serveur.commitAppele)
    }

    @Test fun une_extension_refusee_ne_compte_pas_comme_un_echec() {
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.EXTENSION_REFUSEE))
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0, "a.webm"))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(0, bilan.echecs)
        assertEquals(1, bilan.refuses)
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
    }

    @Test fun une_revocation_arrete_tout_immediatement() {
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.REVOQUE))
        val bilan = Orchestrateur(
            FausseSource(listOf(media(100.0), media(200.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertTrue(bilan.revoque)
        assertEquals(0, bilan.envoyes)
    }

    @Test fun les_medias_deja_connus_ne_sont_pas_envoyes() {
        // Le serveur ne reclame rien : on ne transfere rien, mais on valide
        // quand meme pour faire avancer l'horizon.
        val serveur = FauxServeur(reclame = { emptyList() })
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(0, bilan.envoyes)
        assertTrue(serveur.commitAppele)
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
    }
}
