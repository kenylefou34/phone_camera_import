package fr.izquierdo.phototheque.medias

import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import fr.izquierdo.phototheque.synchro.Dates
import fr.izquierdo.phototheque.synchro.SourceMedias
import java.io.InputStream

/**
 * Lecture des photos et vidéos par MediaStore.
 *
 * On n'utilise PAS l'accès direct au système de fichiers ni
 * MANAGE_EXTERNAL_STORAGE : MediaStore suffit, donne RELATIVE_PATH (donc la
 * liste des dossiers sans parcourir le disque) et reste dans les permissions
 * étroites READ_MEDIA_IMAGES / READ_MEDIA_VIDEO.
 */
class Depot(private val context: Context) : SourceMedias {

    private val colonnes = arrayOf(
        MediaStore.MediaColumns._ID,
        MediaStore.MediaColumns.DISPLAY_NAME,
        MediaStore.MediaColumns.RELATIVE_PATH,
        MediaStore.MediaColumns.SIZE,
        MediaStore.MediaColumns.DATE_MODIFIED,
        MediaStore.MediaColumns.DATE_TAKEN,
    )

    override fun lister(): List<Media> =
        interroger(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, estVideo = false) +
        interroger(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, estVideo = true)

    private fun interroger(uri: Uri, estVideo: Boolean): List<Media> {
        val resultat = mutableListOf<Media>()
        context.contentResolver.query(uri, colonnes, null, null, null)?.use { c ->
            val iId = c.getColumnIndexOrThrow(MediaStore.MediaColumns._ID)
            val iNom = c.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME)
            val iChemin = c.getColumnIndexOrThrow(MediaStore.MediaColumns.RELATIVE_PATH)
            val iTaille = c.getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE)
            val iModif = c.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_MODIFIED)
            val iPrise = c.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_TAKEN)
            while (c.moveToNext()) {
                val prise = if (c.isNull(iPrise)) null else c.getLong(iPrise)
                resultat += Media(
                    id = c.getLong(iId),
                    // RELATIVE_PATH finit par « / » : on la retire pour que le
                    // dossier corresponde exactement aux clés d'horizon du serveur.
                    // La colonne est nullable en interne à MediaProvider (qui lui-
                    // même applique un repli) : sans le « ?: "" », une seule ligne
                    // aberrante lèverait une NPE non rattrapée par Orchestrateur et
                    // ferait échouer toute la synchronisation.
                    dossier = (c.getString(iChemin) ?: "").trimEnd('/'),
                    nom = c.getString(iNom),
                    taille = c.getLong(iTaille),
                    instant = Dates.instantSecondes(prise, c.getLong(iModif)),
                    // Connu par l'URI de collection interrogée : jamais redeviné
                    // depuis l'extension du nom (qui peut manquer).
                    estVideo = estVideo,
                )
            }
        }
        return resultat
    }

    override fun ouvrir(media: Media): InputStream {
        // Le type vient de la collection qui a produit la ligne, jamais de
        // l'extension du nom : un fichier sans extension serait sinon cherché
        // dans la mauvaise collection.
        val base = if (media.estVideo) MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                   else MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        val uri = ContentUris.withAppendedId(base, media.id)
        return context.contentResolver.openInputStream(uri)
            ?: throw java.io.IOException("media illisible : ${media.chemin}")
    }

    /** Dossiers présents sur le téléphone et nombre de médias de chacun. */
    fun dossiers(): Map<String, Int> =
        lister().groupingBy { it.dossier }.eachCount()

    /**
     * Vrai si l'utilisateur n'a accordé l'accès qu'à UNE SÉLECTION de photos
     * (Android 14+). L'application fonctionnerait alors normalement en ne
     * sauvegardant que celles-là : c'est le mode de panne silencieux que la
     * conception veut rendre impossible. À afficher en permanence.
     */
    fun accesPartiel(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return false
        val complet = context.checkSelfPermission(
            android.Manifest.permission.READ_MEDIA_IMAGES) == PackageManager.PERMISSION_GRANTED
        val partiel = context.checkSelfPermission(
            "android.permission.READ_MEDIA_VISUAL_USER_SELECTED") == PackageManager.PERMISSION_GRANTED
        return !complet && partiel
    }
}
