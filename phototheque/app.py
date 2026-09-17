"""Application FastAPI du service d'ingestion."""

import base64
import datetime
import json

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from mediasort.catalog import Catalog
from mediasort.hashing import file_hash
from . import adminauth, config, ingest, pairing, sessions, stats, tls, web
from .devices import DeviceStore

app = FastAPI(title="phototheque")

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


def require_admin(authorization: str = Header(default="")) -> None:
    """Dépendance d'auth admin : « Authorization: Basic <utilisateur:secret> ».

    Le navigateur affiche sa propre fenêtre de connexion dès qu'on répond 401
    avec l'en-tête WWW-Authenticate. Sans cet en-tête il n'affiche rien.

    Un fichier de mot de passe absent ferme l'administration : le service n'a
    pas encore été installé par deploy/install.sh, mieux vaut refuser que
    laisser la surface ouverte.
    """
    refus = HTTPException(
        status_code=401, detail="authentification requise",
        headers={"WWW-Authenticate": 'Basic realm="phototheque"'},
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
        raise refus
    try:
        identifiants = base64.b64decode(authorization[len(prefixe):]).decode()
        utilisateur, _, secret = identifiants.partition(":")
    except (ValueError, UnicodeDecodeError):
        raise refus
    if utilisateur != "admin" or not adminauth.verifier(secret, enregistre):
        raise refus


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
async def sync_upload(session: str = Form(...), path: str = Form(...),
                      file: UploadFile = File(...), _: str = Depends(require_device)) -> dict:
    contenu = await file.read()
    try:
        dest = sessions.save_upload(config.INCOMING_DIR, session, path, contenu)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "hash": file_hash(dest)}


@app.post("/sync/commit")
def sync_commit(req: CommitRequest, dev_id: str = Depends(require_device)) -> dict:
    session_dir = config.INCOMING_DIR / req.session
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="session inconnue")
    cat = Catalog(config.CATALOG_DB)
    try:
        bilan = ingest.sort_session(session_dir, config.LIBRARY_DIR, cat)
    finally:
        cat.close()
    sessions.cleanup(config.INCOMING_DIR, req.session)
    # L'horizon n'avance QU'APRÈS un tri réussi : si la synchro échoue en
    # route, la prochaine reprend depuis le dernier point sûr. On peut
    # reproposer deux fois les mêmes fichiers — l'anti-doublon les écarte —
    # mais on ne peut jamais en perdre.
    for dossier, ts in req.horizons.items():
        devices().set_horizon(dev_id, dossier, ts)
    return bilan


@app.get("/sync/horizon")
def sync_horizon(dev_id: str = Depends(require_device)) -> dict:
    """Indique à l'application depuis quand remonter les médias.

    'dossiers' donne les horizons déjà atteints. Pour un dossier absent de
    cette liste, l'application utilise son propre .flagfile_timestamp s'il
    existe (il reprend là où run_backup.sh s'était arrêté), sinon 'depuis'.
    'depuis' vaut null pour un appareil appairé avant l'introduction de ce
    réglage : aucune limite.
    """
    store = devices()
    return {"depuis": store.get_horizon_initial(dev_id),
            "dossiers": store.get_horizons(dev_id)}


# ---- surface d'admin, protégée par mot de passe (issue #10) ----
@app.get("/devices")
def list_devices(_: None = Depends(require_admin)) -> list:
    return devices().list()


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
    """
    try:
        return tls.empreinte_certificat(config.CERT_FILE)
    except OSError:
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

    La date proposée est l'horizon déjà enregistré pour cet appareil s'il y
    en a un (retour sur la page après un POST), sinon aujourd'hui — repli
    qui évite de remonter tout l'historique d'un téléphone neuf.
    """
    identifiant, _ = _appairage_en_cours
    depuis = (devices().get_horizon_initial(identifiant)
              or datetime.date.today().isoformat())
    return web.pair_html(pairing.qr_svg(charge_appairage()),
                         config.PUBLIC_URL, depuis)


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


@app.post("/pair", response_class=HTMLResponse)
def pair_depuis(depuis: str = Form(...), _: None = Depends(require_admin)) -> str:
    """Enregistre la date à partir de laquelle l'appareil remontera ses médias.

    Revérifie la fraîcheur de l'appairage avant d'écrire : une page restée
    ouverte plus de 10 minutes verrait son appairage purgé entre-temps, et
    sans ce contrôle la date serait écrite sur une ligne disparue avant de
    réafficher un QR pointant vers un appareil inexistant.
    """
    try:
        datetime.date.fromisoformat(depuis)
    except ValueError:
        raise HTTPException(status_code=400, detail="date invalide (AAAA-MM-JJ)")
    _assurer_appairage_en_cours()
    identifiant, _secret = _appairage_en_cours
    devices().set_horizon_initial(identifiant, depuis)
    return _page_appairage()


@app.get("/", response_class=HTMLResponse)
def admin(_: None = Depends(require_admin)) -> str:
    d = stats.disk_stats(config.LIBRARY_DIR)
    return web.admin_html(devices().list(), d, _media_counts())
