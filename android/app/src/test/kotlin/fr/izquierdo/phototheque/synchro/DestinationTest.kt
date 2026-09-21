package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

class DestinationTest {

    // 2025-09-27 14:48:22 UTC
    private val septembre2025 = 1759000102.0

    @Test fun une_photo_va_dans_Photos_annee_mois() {
        assertEquals("Photos/2025/09 SEPTEMBRE",
            Destination.dossier(septembre2025, estVideo = false,
                                cheminSource = "DCIM/Camera/IMG.jpg"))
    }

    @Test fun une_video_va_dans_Videos() {
        assertEquals("Videos/2025/09 SEPTEMBRE",
            Destination.dossier(septembre2025, estVideo = true,
                                cheminSource = "DCIM/Camera/VID.mp4"))
    }

    @Test fun un_media_whatsapp_passe_sous_le_dossier_WhatsApp() {
        assertEquals("WhatsApp/Photos/2025/09 SEPTEMBRE",
            Destination.dossier(septembre2025, estVideo = false,
                                cheminSource = "Pictures/WhatsApp/IMG.jpg"))
    }

    @Test fun la_detection_whatsapp_ignore_la_casse() {
        // Le serveur teste `"whatsapp" in part.lower()` : une ROM qui ecrit
        // « whatsapp » en minuscules doit ranger au meme endroit.
        assertEquals("WhatsApp/Videos/2025/09 SEPTEMBRE",
            Destination.dossier(septembre2025, estVideo = true,
                                cheminSource = "Movies/whatsapp/VID.mp4"))
    }

    @Test fun les_mois_portent_le_nom_francais_en_majuscules() {
        // 2026-01-15 et 2026-08-16 (UTC) : janvier et aout, sans accent
        // circonflexe — le serveur ecrit « AOUT », pas « AOÛT ».
        assertEquals("Photos/2026/01 JANVIER",
            Destination.dossier(1768435200.0, false, "DCIM/Camera/a.jpg"))
        assertEquals("Photos/2026/08 AOUT",
            Destination.dossier(1786838400.0, false, "DCIM/Camera/a.jpg"))
    }
}
