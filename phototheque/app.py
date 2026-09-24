"""Application FastAPI du service d'ingestion."""

import base64
import json
import logging
import math
import time
from pathlib import Path

from fastapi import (Depends, FastAPI, File, Form, Header, HTTPException,
                     Request, UploadFile)
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from mediasort import classify
from mediasort.catalog import Catalog
from mediasort.hashing import file_hash
from . import (adminauth, apk, config, essais, ingest, pairing, quarantaine,
               sessions, stats, tls, web)
from .devices import DeviceStore

# docs_url/redoc_url/openapi_url à None = les routes n'existent pas du tout,
# et répondent donc 404. C'est voulu : un 401 annoncerait ce qu'il protège.
app = FastAPI(
    title="phototheque",
    docs_url="/docs" if config.DOCS_PUBLIQUES else None,
    redoc_url="/redoc" if config.DOCS_PUBLIQUES else None,
    openapi_url="/openapi.json" if config.DOCS_PUBLIQUES else None,
)

_devices = None


def devices() -> DeviceStore:
    """Ouvre la base des appareils à la PREMIÈRE UTILISATION, pas à l'import.

    Instancier DeviceStore au chargement du module ferait qu'un simple
    « import phototheque.app » créerait le fichier SQLite dans le dossier
    personnel — y compris en lançant les tests ou un outil quelconque. Cela a
    déjà cassé un déploiement (17/09/2026) : la base vide ainsi créée a fait
    croire au script d'installation que la reprise des appairages était faite.
    """
    global _devices
    if _devices is None:
        _devices = DeviceStore(config.DEVICES_DB)
    return _devices


def require_device(authorization: str = Header(default="")) -> str:
    """Dépendance d'auth : exige 'Authorization: Bearer <secret>' valide."""
    prefixe = "Bearer "
    secret = authorization[len(prefixe):] if authorization.startswith(prefixe) else ""
    dev_id = devices().validate(secret) if secret else None
    if not dev_id:
        raise HTTPException(status_code=401, detail="jeton invalide")
    return dev_id


# Journal des échecs d'authentification : visible dans « journalctl -u
# phototheque ». Personne ne surveille ce service en permanence, mais une trace
# permet au moins de comprendre APRÈS COUP qu'on s'y est acharné.
_journal = logging.getLogger("phototheque.admin")

# Décompte des essais ratés, par machine d'origine (issue #19). Un seul pour
# tout le processus : c'est l'état partagé qui permet de refuser sans calculer.
_limiteur = essais.Limiteur()


def require_admin(request: Request, authorization: str = Header(default="")) -> None:
    """Dépendance d'auth admin : « Authorization: Basic <utilisateur:secret> ».

    Le navigateur affiche sa propre fenêtre de connexion dès qu'on répond 401
    avec l'en-tête WWW-Authenticate. Sans cet en-tête il n'affiche rien.

    Un fichier de mot de passe absent ferme l'administration : le service n'a
    pas encore été installé par deploy/install.sh, mieux vaut refuser que
    laisser la surface ouverte.

    L'identifiant, lui, est relu à chaque requête comme le mot de passe : les
    changer ne demande donc aucun redémarrage. Son absence vaut « admin »
    (voir adminauth.utilisateur) ; c'est le mot de passe qui protège, pas ce
    nom.
    """
    refus = HTTPException(
        status_code=401, detail="authentification requise",
        headers={"WWW-Authenticate": 'Basic realm="phototheque"'},
    )
    source = request.client.host if request.client else "inconnue"

    # AVANT toute lecture de fichier et tout calcul : c'est tout l'objet de la
    # limitation. Vérifier puis refuser laisserait intact le levier de
    # saturation — chaque essai coûte ~100 ms des deux cœurs du NUC, dans le
    # processus qui fait aussi le tri des médias.
    attente = _limiteur.doit_attendre(source, time.monotonic())
    if attente > 0:
        raise HTTPException(
            status_code=429,
            detail=f"trop d'essais — réessayez dans {math.ceil(attente)} secondes",
            headers={"Retry-After": str(math.ceil(attente))},
        )

    try:
        enregistre = config.ADMIN_FILE.read_text().strip()
    except (OSError, ValueError):
        # OSError : fichier absent (service pas encore installé).
        # ValueError : contenu non décodable (corruption). Dans les deux cas
        # on refuse proprement plutôt que de renvoyer une erreur serveur.
        raise refus
    prefixe = "Basic "
    if not authorization.startswith(prefixe):
        # PAS un échec : le navigateur envoie TOUJOURS une première requête
        # sans identifiants, et n'affiche sa fenêtre de connexion qu'après
        # avoir reçu ce 401. Compter ce passage obligé épuiserait le quota du
        # mainteneur en navigation parfaitement normale — quelques pages
        # ouvertes suffiraient à le bloquer.
        raise refus
    try:
        identifiants = base64.b64decode(authorization[len(prefixe):]).decode()
        utilisateur, _, secret = identifiants.partition(":")
    except (ValueError, UnicodeDecodeError):
        raise refus
    attendu = adminauth.utilisateur(config.ADMIN_USER_FILE)
    if utilisateur != attendu or not adminauth.verifier(secret, enregistre):
        nb = _limiteur.echec(source, time.monotonic())
        if nb >= essais.SEUIL:
            _journal.warning(
                "authentification d'administration : %d échecs consécutifs "
                "depuis %s", nb, source)
        raise refus
    # Réussite : on efface l'ardoise, le mainteneur ne traîne pas ses fautes
    # de frappe de la veille.
    _limiteur.succes(source)


def _media_counts() -> dict:
    return stats.media_stats(config.CATALOG_DB) if config.CATALOG_DB.exists() else {"photos": 0, "videos": 0}


# ---- surface authentifiée (utilisée par l'app) ----
@app.get("/status")
def status(_: str = Depends(require_device)) -> dict:
    d = stats.disk_stats(config.LIBRARY_DIR)
    m = _media_counts()
    return {"ok": True, "library": str(config.LIBRARY_DIR),
            "catalog_count": m["photos"] + m["videos"], "disque": d, "medias": m}


class FileSig(BaseModel):
    path: str
    size: int
    hash: str


class PlanRequest(BaseModel):
    files: list[FileSig]


class CommitRequest(BaseModel):
    session: str
    # Jusqu'où chaque dossier a été parcouru par l'application. Facultatif :
    # un client qui ne l'envoie pas continue de fonctionner.
    horizons: dict[str, float] = {}


@app.post("/sync/plan")
def sync_plan(req: PlanRequest, _: str = Depends(require_device)) -> dict:
    cat = Catalog(config.CATALOG_DB)
    try:
        manquants = [f.hash for f in req.files if not cat.has_hash(f.hash)]
    finally:
        cat.close()
    return {"session": sessions.new_session(), "needed": manquants}


@app.post("/sync/upload")
def sync_upload(session: str = Form(...), path: str = Form(...),
                file: UploadFile = File(...), _: str = Depends(require_device)) -> dict:
    """Reçoit un média. Refuse les extensions que le trieur ne sait pas ranger.

    Fonction SYNCHRONE (`def` et non `async def`), volontairement : FastAPI
    exécute alors le corps dans un fil d'exécution séparé, si bien que la
    recopie du fichier — qui peut durer des minutes sur une vidéo de plusieurs
    gigaoctets — ne bloque pas la boucle d'événements et n'empêche pas le
    service de répondre. On y accède au flux brut (`file.file`) plutôt qu'au
    `await file.read()` d'avant, qui ramenait TOUT le fichier en mémoire
    (issue #21).

    Sans ce refus, le média était perdu en silence : accepté ici (« bien
    reçu »), ignoré par le trieur qui ne connaît pas l'extension, supprimé
    avec le dossier de session, et l'horizon avançait quand même puisque le
    bilan ne comptait aucune erreur. Le téléphone ne le reproposait jamais.

    On refuse plutôt que de bloquer l'horizon : bloquer créerait un blocage
    PERMANENT (le téléphone repropose, le fichier est ignoré, l'horizon
    n'avance jamais pour ce dossier). Refuser garde le fichier sur le
    téléphone, donne un signal clair à l'application, et laisse l'horizon
    avancer pour tout le reste.
    """
    extension = Path(path).suffix
    if classify.media_type(extension) is None:
        raise HTTPException(
            status_code=400,
            detail=f"extension non prise en charge : « {extension or path} » —"
                   " le serveur n'accepte que les photos et vidéos qu'il sait ranger",
        )
    try:
        dest = sessions.save_upload(config.INCOMING_DIR, session, path, file.file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "hash": file_hash(dest)}


@app.post("/sync/commit")
def sync_commit(req: CommitRequest, dev_id: str = Depends(require_device)) -> dict:
    """Range les fichiers reçus, puis fait avancer les horizons.

    Une session SANS DOSSIER n'est pas une session inconnue : c'est une
    session vide, cas parfaitement normal. `new_session()` ne crée rien, le
    dossier n'apparaît qu'au premier envoi ; or en régime permanent — la
    bibliothèque à jour — une synchro n'a souvent rien à envoyer. Répondre 404
    empêchait alors l'horizon d'avancer, et le téléphone rescannait
    indéfiniment la même fenêtre. On traite donc ce cas comme un tri à zéro
    fichier.

    Le contrôle qui reste est celui de la FORME de l'identifiant : seule la
    forme produite par `new_session()` est acceptée (voir
    sessions.identifiant_valide), ce qui interdit aussi bien un nom
    fantaisiste qu'un identifiant remontant hors du dépôt des envois.
    """
    if not sessions.identifiant_valide(req.session):
        raise HTTPException(status_code=404, detail="session inconnue")
    session_dir = config.INCOMING_DIR / req.session
    if session_dir.exists():
        cat = Catalog(config.CATALOG_DB)
        try:
            bilan = ingest.sort_session(session_dir, config.LIBRARY_DIR, cat)
        finally:
            cat.close()
    else:
        bilan = ingest.bilan_vide()      # session vide : rien n'a été envoyé
    # AVANT le nettoyage, impérativement : `sessions.cleanup` supprime le
    # dossier de session en entier, et un fichier que le tri n'a pas su ranger
    # y est resté. C'est ainsi que le serveur détruisait les médias qu'il
    # n'avait pas rangés (issue #16). Seule la liste `echecs` dit quoi sauver :
    # ce qui reste dans la session contient aussi les doublons et le bruit
    # exclu, qu'on a raison de détruire.
    if bilan["echecs"]:
        quarantaine.mettre_de_cote(
            session_dir, bilan["echecs"],
            config.INCOMING_DIR / quarantaine.DOSSIER)
    sessions.cleanup(config.INCOMING_DIR, req.session)
    # L'horizon n'avance qu'après un tri INTÉGRALEMENT réussi. Avancer dirait
    # au téléphone « bien reçu » pour un média que la bibliothèque n'a pas ;
    # il ne le proposerait plus jamais. On préfère qu'il repropose tout le
    # dossier ; l'anti-doublon écartera les fichiers déjà rangés sans les
    # transférer. La quarantaine ci-dessus est la ceinture : même si le
    # téléphone ne repasse jamais, le média existe encore sur le NUC.
    if bilan["errors"] == 0:
        # Borne haute : un horodatage dans le futur — horloge d'appareil photo
        # mal réglée, bug de l'application, valeur aberrante — FERMERAIT
        # définitivement le dossier, puisque toute photo suivante serait sous
        # l'horizon et ne serait plus jamais proposée. Le sens inverse est
        # bénin : un horizon qui recule fait reproposer des fichiers déjà
        # connus, que l'anti-doublon écarte sans les transférer.
        maintenant = time.time()
        for dossier, ts in req.horizons.items():
            # Une valeur non finie ne peut pas être bornée : min(nan, x) vaut
            # nan — la seule valeur que min() ne rattrape pas — SQLite
            # l'enregistre en NULL et la contrainte NOT NULL de
            # horizons.dernier_ts lève, ce qui renvoyait une erreur 500 au
            # téléphone après avoir écrit les horizons À MOITIÉ. Et -inf
            # passait la borne, était enregistré, puis ressortait en `null`
            # de /sync/horizon : contrat `dossiers: dict[str, float]` cassé.
            # On ignore le dossier fautif plutôt que de rejeter tout l'envoi :
            # un horodatage aberrant sur un dossier ne doit pas faire échouer
            # la synchro des autres, ni empêcher de valider des médias déjà
            # rangés. Silencieusement, faute de journal dans ce module.
            #
            # Le contrôle porte sur la valeur BORNÉE et non sur `ts` : c'est
            # ce qu'on s'apprête à écrire qui doit être un instant réel. +inf
            # est ainsi ramené à maintenant, comme il l'était déjà — le borner
            # fonctionne parfaitement — tandis que nan et -inf, que min() ne
            # rattrape pas, sont les seuls écartés.
            horizon = min(ts, maintenant)
            if not math.isfinite(horizon):
                continue
            devices().set_horizon(dev_id, dossier, horizon)
    return bilan


@app.get("/sync/horizon")
def sync_horizon(dev_id: str = Depends(require_device)) -> dict:
    """Indique à l'application depuis quand remonter les médias.

    'dossiers' donne les horizons déjà atteints. Pour un dossier absent de
    cette liste, l'application utilise son propre .flagfile_timestamp s'il
    existe (il reprend là où run_backup.sh s'était arrêté), sinon 'depuis'.
    'depuis' vaut la date d'appairage — posée dès la création de l'appairage,
    même si personne n'a validé le formulaire. Il ne vaut null que pour un
    appareil repris d'une base antérieure à ce réglage : aucune limite, on ne
    restreint pas rétroactivement ce qu'il avait le droit d'envoyer.
    """
    store = devices()
    return {"depuis": store.get_horizon_initial(dev_id),
            "dossiers": store.get_horizons(dev_id)}


@app.post("/sync/desappairer")
def sync_desappairer(dev_id: str = Depends(require_device)) -> dict:
    """Permet au téléphone de se retirer LUI-MÊME (lot 2).

    La seule révocation existante, `POST /devices/{id}/revoke`, est derrière
    `require_admin` : le téléphone ne détient qu'un jeton d'appareil et ne peut
    pas l'appeler.

    Le risque est mesuré : un jeton volé permettrait de révoquer le téléphone
    légitime, qui se réappairerait. C'est un désagrément, à comparer à ce que
    le même jeton volé permet déjà — déposer des médias.

    L'application efface son état local QUOI QU'IL ARRIVE, sans attendre cette
    réponse : au moment précis où l'on désappaire pour se dépanner, le serveur
    est le plus souvent injoignable.
    """
    return {"retire": devices().revoke(dev_id)}


# ---- surface d'admin, protégée par mot de passe (issue #10) ----
@app.get("/devices")
def list_devices(_: None = Depends(require_admin)) -> list:
    return devices().list()


@app.post("/echecs/purge")
def purge_echecs(_: None = Depends(require_admin)) -> dict:
    """Vide la quarantaine des médias que le tri n'a pas su ranger (issue #16).

    Derrière le mot de passe d'administration : c'est la seule route du
    serveur qui supprime des médias sur commande. La purge reste manuelle,
    jamais automatique — une purge à l'ancienneté redeviendrait le défaut
    qu'on a corrigé, avec un délai.
    """
    return {"retires": quarantaine.purger(
        config.INCOMING_DIR / quarantaine.DOSSIER)}


@app.post("/devices/{device_id}/revoke")
def revoke_device(device_id: str, _: None = Depends(require_admin)) -> dict:
    return {"revoked": devices().revoke(device_id)}


# Appairage actuellement proposé : (id, secret en clair). Gardé en mémoire
# uniquement — le secret n'est jamais écrit sur disque, seule son empreinte
# l'est. Perdu au redémarrage du service, ce qui est sans conséquence : la
# page en proposera simplement un nouveau.
_appairage_en_cours = None


def _empreinte_du_certificat():
    """Empreinte du certificat servi, ou None s'il n'y en a pas.

    Absent = service lancé à la main en HTTP pour du développement. On ne
    casse pas la page d'appairage pour autant ; l'application saura que le
    serveur n'est pas épinglable.

    Abîmé = même traitement. `empreinte_certificat` lit le fichier en texte
    puis le décode : un PEM tronqué ou vide lève ValueError, un contenu
    binaire UnicodeDecodeError (qui en dérive). Le cas est atteignable — un
    `openssl req` interrompu, une copie de migration coupée — et n'attraper
    qu'OSError transformait un fichier abîmé en erreur 500 sur /pair.
    """
    try:
        return tls.empreinte_certificat(config.CERT_FILE)
    except (OSError, ValueError):
        return None


def charge_appairage() -> str:
    """Le JSON encodé dans le QR : où joindre le serveur, jeton, empreinte."""
    _, secret = _appairage_en_cours
    return json.dumps(pairing.pairing_payload(
        config.PUBLIC_URL, secret, _empreinte_du_certificat()))


def _assurer_appairage_en_cours() -> None:
    """Garantit qu'un appairage valable est en cours ; en crée un sinon.

    Appelée par GET comme par POST : sans cela, une page laissée ouverte
    au-delà du délai verrait son appairage purgé, et POST écrirait la date
    sur une ligne disparue avant de réafficher un QR inutilisable.
    """
    global _appairage_en_cours
    devices().purge_pending()
    if _appairage_en_cours is not None:
        identifiant, _ = _appairage_en_cours
        if not devices().is_pending(identifiant):
            _appairage_en_cours = None      # confirmé, expiré ou révoqué
    if _appairage_en_cours is None:
        _appairage_en_cours = devices().pair("Nouveau téléphone")


def _page_appairage() -> str:
    """Rend la page d'appairage pour l'appairage en cours.

    Elle ne propose plus de date de départ (constat C5, recette du 24/09) :
    le téléphone règle la sienne et la fait toujours primer. L'horizon par
    défaut reste posé par Devices.pair(), pour un téléphone sans date.
    """
    return web.pair_html(pairing.qr_svg(charge_appairage()), config.PUBLIC_URL)


@app.get("/pair", response_class=HTMLResponse)
def pair(_: None = Depends(require_admin)) -> str:
    """Affiche le QR d'appairage. Un GET ne doit RIEN créer de nouveau.

    Recharger la page réaffiche le même QR tant qu'il est valable. Sans cela,
    chaque appel fabriquait une clé d'accès : sonde de supervision,
    préchargement du navigateur, vérification du script d'installation...
    Un appairage neuf n'est émis qu'une fois le précédent utilisé par un
    téléphone, expiré, ou révoqué.
    """
    _assurer_appairage_en_cours()
    return _page_appairage()


@app.get("/", response_class=HTMLResponse)
def admin(_: None = Depends(require_admin)) -> str:
    d = stats.disk_stats(config.LIBRARY_DIR)
    return web.admin_html(devices().list(), d, _media_counts(),
                          apk.infos(config.APK_FILE),
                          quarantaine.lister(
                              config.INCOMING_DIR / quarantaine.DOSSIER))


@app.get("/apk")
def apk_telecharger(_: None = Depends(require_admin)) -> FileResponse:
    """Sert l'APK déposé par deploy/envoyer-apk.sh.

    Derrière le mot de passe, comme le reste de l'administration. Le binaire
    n'a rien de secret — il est inutilisable sans un QR d'appairage — mais un
    service qui distribue un exécutable à tout le réseau sans rien demander
    reste une porte qu'on n'a aucune raison d'ouvrir.

    Le 404 explique quoi faire : sans cela, un service fraîchement installé
    répondrait « non trouvé » et donnerait l'impression que la fonction est
    cassée, alors qu'il manque seulement un dépôt.
    """
    vu = apk.infos(config.APK_FILE)
    if vu is None:
        raise HTTPException(
            status_code=404,
            detail="Aucune application déposée sur ce serveur. Lancez "
                   "./deploy/envoyer-apk.sh depuis la machine de compilation.")
    return FileResponse(config.APK_FILE, media_type=apk.TYPE_MIME,
                        filename=apk.nom_de_telechargement(vu))
