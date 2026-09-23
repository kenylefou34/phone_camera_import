package fr.izquierdo.phototheque.synchro

/**
 * Un dossier de l'arborescence présentée à l'utilisateur.
 *
 * [chemin] est le chemin RÉEL, celui que porte `Media.dossier` et qui sert de
 * clé d'horizon côté serveur. [libelle] est ce qu'on affiche : il peut contenir
 * des « / » quand une chaîne de dossiers vides a été repliée.
 */
data class Noeud(
    val chemin: String,
    val libelle: String,
    /** Médias DIRECTEMENT dans ce dossier, sans les sous-dossiers. */
    val medias: Int,
    /** Médias de ce dossier ET de toute sa descendance. */
    val mediasTotal: Int,
    val enfants: List<Noeud>,
)

/**
 * Construction de l'arborescence à partir des chemins plats de MediaStore.
 *
 * MediaStore ne connaît pas d'arbre : `RELATIVE_PATH` rend « Pictures/WhatsApp »
 * sans dire que « Pictures » existe. C'est ici qu'on le reconstitue.
 */
object Arbre {

    fun construire(dossiers: Map<String, Int>): List<Noeud> {
        val racine = Brouillon("")
        for ((chemin, nombre) in dossiers) {
            var courant = racine
            for (segment in chemin.split("/").filter { it.isNotEmpty() }) {
                courant = courant.enfants.getOrPut(segment) { Brouillon(segment) }
            }
            courant.medias += nombre
        }
        return racine.enfants.values.map { figer(it, "") }.sortedBy { it.libelle }
    }

    private class Brouillon(val segment: String) {
        val enfants = linkedMapOf<String, Brouillon>()
        var medias = 0
    }

    private fun figer(depart: Brouillon, prefixe: String): Noeud {
        var noeud = depart
        var libelle = depart.segment
        var chemin = if (prefixe.isEmpty()) depart.segment else "$prefixe/${depart.segment}"
        // Repli : un dossier SANS média et à enfant UNIQUE n'apprend rien et
        // coûte un appui. Les deux conditions comptent — un dossier qui
        // contient des médias doit rester cochable pour lui-même.
        while (noeud.medias == 0 && noeud.enfants.size == 1) {
            val unique = noeud.enfants.values.first()
            libelle += "/${unique.segment}"
            chemin += "/${unique.segment}"
            noeud = unique
        }
        val enfants = noeud.enfants.values.map { figer(it, chemin) }.sortedBy { it.libelle }
        return Noeud(
            chemin = chemin,
            libelle = libelle,
            medias = noeud.medias,
            mediasTotal = noeud.medias + enfants.sumOf { it.mediasTotal },
            enfants = enfants)
    }
}
