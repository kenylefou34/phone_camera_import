package fr.izquierdo.phototheque.synchro

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Le bouton « Interrompre » de la notification.
 *
 * Un BroadcastReceiver et non une activite : la conception veut qu'on puisse
 * arreter SANS rouvrir l'application. Et un PendingIntent d'activite ne
 * delivre meme pas son intent quand la tache existe deja en arriere-plan —
 * le systeme se contente de la ramener au premier plan.
 */
class RecepteurInterruption : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == ServiceSynchro.ACTION_INTERROMPRE) {
            TravailSynchro.interrompre(context)
        }
    }
}
