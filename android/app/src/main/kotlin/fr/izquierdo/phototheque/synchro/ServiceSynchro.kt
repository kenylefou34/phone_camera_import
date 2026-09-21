package fr.izquierdo.phototheque.synchro

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.ForegroundInfo

/**
 * La notification qui accompagne une synchronisation en arrière-plan.
 *
 * Android l'exige pour un service de premier plan, mais elle a ici un vrai
 * rôle : écran éteint, c'est le SEUL endroit où l'avancement est visible, et
 * le seul endroit d'où l'on peut arrêter sans rouvrir l'application.
 *
 * Le nom du fichier en cours n'y figure pas : il change toutes les secondes et
 * ferait clignoter la notification en permanence.
 */
object ServiceSynchro {

    private const val CANAL = "synchro"
    private const val ID = 1

    const val ACTION_INTERROMPRE = "fr.izquierdo.phototheque.INTERROMPRE"

    fun information(context: Context, avancement: Avancement): ForegroundInfo {
        creerCanal(context)

        val titre = when (avancement.phase) {
            Phase.ANALYSE -> "Analyse ${avancement.fichiersFaits} / ${avancement.fichiersTotal}"
            Phase.ENVOI -> "Sauvegarde ${avancement.fichiersFaits} / ${avancement.fichiersTotal}"
            Phase.RANGEMENT -> "Rangement sur le serveur…"
        }
        val vitesse = avancement.octetsParSeconde
            ?.let { " · %.1f Mo/s".format(it / 1_048_576.0) } ?: ""

        // getBroadcast et non getActivity : la conception veut arreter SANS
        // rouvrir l'application, et un PendingIntent d'activite ne delivre
        // meme pas son intent quand la tache existe deja en arriere-plan (le
        // systeme se contente de la ramener au premier plan). Voir
        // RecepteurInterruption.
        val arret = PendingIntent.getBroadcast(
            context, 0,
            Intent(context, RecepteurInterruption::class.java).setAction(ACTION_INTERROMPRE),
            PendingIntent.FLAG_IMMUTABLE)

        val notification = NotificationCompat.Builder(context, CANAL)
            .setContentTitle(titre)
            .setContentText("${avancement.pourcentage} %$vitesse")
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setOngoing(true)
            .setProgress(100, avancement.pourcentage, avancement.octetsTotal == 0L)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel,
                       "Interrompre", arret)
            .build()

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
            ForegroundInfo(ID, notification,
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else ForegroundInfo(ID, notification)
    }

    // Cree au plus une fois : recreer le canal a chaque appel de information()
    // (donc jusqu'a deux fois par media) rearmait un binder vers le systeme
    // pour rien.
    private var canalCree = false

    private fun creerCanal(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        if (canalCree) return
        val gestionnaire = context.getSystemService(NotificationManager::class.java)
        // IMPORTANCE_LOW : visible et persistante, mais sans son ni vibration.
        // Une sauvegarde d'une heure qui sonne serait desinstallee le jour meme.
        gestionnaire.createNotificationChannel(NotificationChannel(
            CANAL, "Sauvegarde en cours", NotificationManager.IMPORTANCE_LOW))
        canalCree = true
    }
}
