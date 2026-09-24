"""Application FastAPI du service d'ingestion."""

import base64
import json
import logging
import math
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (Depends, FastAPI, File, Form, Header, HTTPException,
                     Request, UploadFile)
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from mediasort import classify
from mediasort.catalog import Catalog
from mediasort.hashing import file_hash
from . import (adminauth, apk, config, essais, ingest, pairing, quarantaine,
               sessions, stats, tls, web)
from .devices import DeviceStore
from .journal import Journal

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


_journal_ouvert = None


def journal() -> Journal:
    """Ouvre le journal à la PREMIÈRE UTILISATION (voir devices())."""
    global _journal_ouvert
    if _journal_ouvert is None:
        _journal_ouvert = Journal(config.JOURNAL_DB)
    return _journal_ouvert


_log_journal = logging.getLogger("phototheque.journal")


def _journaliser(action, message: str = "écriture du journal impossible") -> bool:
    """Écrit dans le journal sans JAMAIS faire échouer la route appelante.

    Un journal en panne (base verrouillée, disque plein) qui ferait échouer
    un commit empêcherait l'horizon d'avancer : le téléphone renverrait tout,
    indéfiniment, pour une simple trace. La trace passe après le travail.

    Rend True si l'écriture a réussi, False sinon (l'exception est avalée et
    écrite dans `journalctl` avec `message`). La plupart des appelants
    ignorent ce retour ; `_Disjoncteur` s'en sert pour ne pas insister.
    """
    try:
        action(journal())
        return True
    except Exception:
        _log_journal.exception(message)
        return False


class _Disjoncteur:
    """Coupe les écritures au journal d'UNE opération après le premier échec.

    Une opération = un tri (un commit) ou une passe de purge : une écriture
    par fichier. Une base tenue par un outil extérieur (DB Browser, une
    sauvegarde) fait attendre CHAQUE écriture 5 s avant d'échouer — et
    pendant un tri, sous le verrou qui bloque aussi tous les autres commits.
    Sur 953 fichiers : ~80 minutes de plus, et le téléphone abandonnait à
    30 minutes en annonçant un échec alors que le serveur finissait
    (relecture finale, M3). Au premier échec, les écritures suivantes de la
    même opération ne sont plus tentées : une seule ligne dans `journalctl`,
    un seul délai de 5 s. L'opération suivante (un autre commit) réessaie.
    """

    def __init__(self, message: str) -> None:
        self._message = message
        self.ouvert = False        # « ouvert » comme un disjoncteur : le courant ne passe plus

    def journaliser(self, action) -> bool:
        if self.ouvert:
            return False
        if not _journaliser(action, self._message):
            self.ouvert = True
            return False
        return True


def _purger() -> None:
    """Purge les sessions de synchro abandonnées (spec §5, issue #30).

    Appelée au démarrage du service ET après chaque commit : pas de tâche
    planifiée à installer ni à surveiller. Chaque session emportée laisse un
    événement « purge » dans le journal — personne ne surveille ce service en
    continu, seule une trace permet de comprendre APRÈS COUP qu'un ménage a
    eu lieu. `sessions.purger_abandonnees` isole déjà chaque session dans son
    propre `try/except` (une session à problème n'empêche pas les autres) :
    c'est à l'appelant de décider si une panne plus large (qui remonterait
    quand même jusqu'ici) doit l'arrêter — ici, jamais (voir _cycle_de_vie et
    sync_commit, qui attrapent tous deux `Exception`, pas seulement
    `OSError`).
    """
    for e in sessions.purger_abandonnees(config.INCOMING_DIR):
        # La lambda est appelée tout de suite par _journaliser(), dans cette
        # même itération : pas de piège de capture tardive à contourner ici,
        # `detail` porte déjà la bonne valeur au moment de l'appel.
        detail = f"session {e['session']} : {e['fichiers']} fichier(s), {e['octets']} octets"
        _journaliser(lambda j: j.evenement("purge", detail=detail))


@asynccontextmanager
async def _cycle_de_vie(_app):
    """Au démarrage : trace + purge des sessions abandonnées (spec §5).

    Pas de tâche planifiée à installer ni à surveiller : le service purge en
    s'ouvrant et après chaque commit. Une purge qui échoue ne doit JAMAIS
    empêcher le service de démarrer — `except Exception` et non `except
    OSError` : la règle qui compte est qu'une panne de purge ne bloque
    jamais le démarrage, quelle que soit sa nature (une erreur de
    programmation dans `sessions.purger_abandonnees` ne doit pas non plus
    empêcher le service de répondre), comme `_journaliser` le fait déjà pour
    la même raison.
    """
    _journaliser(lambda j: j.evenement("demarrage"))
    try:
        _purger()
    except Exception:
        _log_journal.exception("purge au démarrage impossible")
    yield


# Affecté après la définition de `_cycle_de_vie` (qui dépend elle-même de
# `_journaliser`, `_purger` et `_log_journal`, tous définis plus haut) : `app`
# est créé en tête de module, avant que ces noms existent. Starlette lit cet
# attribut à chaque démarrage/arrêt de l'application (y compris pour chaque
# `with TestClient(app):`) — l'assigner après coup revient exactement à le
# passer à `FastAPI(lifespan=...)`.
app.router.lifespan_context = _cycle_de_vie


def require_device(request: Request, authorization: str = Header(default="")) -> str:
    """Dépendance d'auth : exige 'Authorization: Bearer <secret>' valide.

    `request` ne sert qu'à connaître l'adresse d'origine, pour l'événement
    « confirmation » (issue #30) : le premier usage réel d'un secret
    d'appairage confirme l'appareil, et c'est l'adresse de CETTE requête-là
    qui dit qui vient de confirmer — pas celle, perdue depuis longtemps, où
    le QR avait été affiché.
    """
    prefixe = "Bearer "
    secret = authorization[len(prefixe):] if authorization.startswith(prefixe) else ""
    adresse = request.client.host if request.client else None

    def _confirme(dev_id: str) -> None:
        _journaliser(lambda j: j.evenement("confirmation", appareil=dev_id, adresse=adresse))

    dev_id = devices().validate(secret, sur_confirmation=_confirme) if secret else None
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
        # SEULEMENT ici, jamais dans la branche « pas d'en-tête Basic » plus
        # haut : celle-ci est le passage obligé du navigateur avant d'afficher
        # sa fenêtre, pas une tentative. Ici, des identifiants ont réellement
        # été présentés et refusés — c'est un échec au sens du journal
        # (issue #30). Le mot de passe lui-même n'y figure jamais.
        _journaliser(lambda j: j.evenement(
            "auth_echec", adresse=source, detail=f"utilisateur « {utilisateur} »"))
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


class BilanApp(BaseModel):
    """Cumul (pas un delta) envoyé par le téléphone, vu de l'application elle-même.

    Facultatif : le journal (issue #30) le garde à côté du bilan calculé côté
    serveur, sans quoi une divergence entre ce que l'app croit avoir envoyé et
    ce que le serveur a réellement rangé passerait inaperçue.

    Chaque compteur est borné (0 à 2**31 - 1) dès la lecture de la requête :
    un nombre négatif ne veut rien dire, et un entier démesuré (10**30) ne
    tient même pas dans une colonne SQLite — il faisait lever l'écriture du
    commit en plein milieu (relecture finale, M2). Hors bornes : 422.
    """
    envoyes: int = Field(default=0, ge=0, le=2**31 - 1)
    refuses: int = Field(default=0, ge=0, le=2**31 - 1)
    echecs: int = Field(default=0, ge=0, le=2**31 - 1)


# Identifiant de synchro accepté du téléphone (lot 1 bis, une grosse
# sauvegarde en plusieurs paquets qui partagent le même identifiant) : forme
# bornée avant d'atteindre la base, sinon une valeur fantaisiste ou trop
# longue produirait une clé imprévisible dans `journal.synchros`.
_MOTIF_SYNCHRO = re.compile(r"[A-Za-z0-9_-]{1,64}")


class CommitRequest(BaseModel):
    session: str
    # Identifiant de la synchro globale (voir _MOTIF_SYNCHRO). Facultatif :
    # un téléphone qui ne l'envoie pas reste journalisé quand même, sous un
    # identifiant fabriqué par le serveur (voir sync_commit, spec §8.2).
    synchro: str | None = None
    # Jusqu'où chaque dossier a été parcouru par l'application. Facultatif :
    # un client qui ne l'envoie pas continue de fonctionner.
    horizons: dict[str, float] = {}
    # Bilan côté application (lot 1 bis / lot 2), facultatif lui aussi.
    bilan_app: BilanApp | None = None


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
        detail = (f"extension non prise en charge : « {extension or path} » —"
                  " le serveur n'accepte que les photos et vidéos qu'il sait ranger")
        # Seulement si l'identifiant de session a la forme attendue : un
        # identifiant fantaisiste (voir sessions.identifiant_valide) n'a rien
        # à faire dans la colonne `session` du journal.
        if sessions.identifiant_valide(session):
            _journaliser(lambda j: j.noter_refus(session, path, detail))
        raise HTTPException(status_code=400, detail=detail)
    try:
        dest = sessions.save_upload(config.INCOMING_DIR, session, path, file.file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "hash": file_hash(dest)}


@app.post("/sync/commit")
def sync_commit(req: CommitRequest, request: Request,
                dev_id: str = Depends(require_device)) -> dict:
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

    Chaque mouvement de fichier part au journal PENDANT le tri, et le commit
    lui-même juste après (issue #30) : la réponse HTTP, elle, GARDE EXACTEMENT
    sa forme actuelle (l'application la lit comme un dictionnaire de
    nombres) — le bilan du journal n'y figure jamais.
    """
    if not sessions.identifiant_valide(req.session):
        raise HTTPException(status_code=404, detail="session inconnue")
    # Un identifiant de synchro hors norme (absent, fantaisiste, trop long)
    # est remplacé par un neuf : un téléphone qui n'envoie rien reste quand
    # même journalisé, sous une seule ligne (spec §8.2).
    synchro = (req.synchro if req.synchro and _MOTIF_SYNCHRO.fullmatch(req.synchro)
              else sessions.new_session())
    session_dir = config.INCOMING_DIR / req.session
    if session_dir.exists():
        # Un disjoncteur par commit (voir _Disjoncteur) : un journal
        # verrouillé ne coûte qu'UN délai au tri, pas un par fichier.
        disjoncteur = _Disjoncteur(
            f"journal indisponible : les mouvements suivants du tri de la "
            f"session {req.session} ne seront pas journalisés")
        cat = Catalog(config.CATALOG_DB)
        try:
            bilan = ingest.sort_session(
                session_dir, config.LIBRARY_DIR, cat,
                sur_mouvement=lambda m: disjoncteur.journaliser(
                    lambda j: j.ajouter_mouvement(req.session, m)))
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
    adresse = request.client.host if request.client else None
    _journaliser(lambda j: j.enregistrer_commit(
        synchro, req.session, dev_id, devices().label(dev_id), adresse, bilan,
        req.bilan_app.model_dump() if req.bilan_app else None))
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
    # APRÈS que les horizons ont été écrits, et dans son propre garde-fou :
    # une purge qui casse ne doit ni changer la réponse du commit (l'app la
    # lit comme un dictionnaire de nombres, voir plus haut) ni empêcher
    # l'horizon d'avoir avancé. `except Exception`, pas seulement `OSError` :
    # même règle qu'au démarrage (_cycle_de_vie) — une purge n'est qu'un
    # ménage, sa panne ne doit JAMAIS se répercuter sur la réponse HTTP.
    #
    # Hypothèse dont dépend cette purge en fin de commit : plus haut,
    # sync_commit traite un dossier de session ABSENT comme une session VIDE
    # et fait quand même avancer l'horizon (voir la docstring de cette
    # fonction). Une session ne doit donc jamais rester inactive plus de
    # 24 h (age_max_s par défaut) entre son premier upload et son commit —
    # vrai aujourd'hui car l'application fait plan/upload/commit en une
    # seule passe (lot 1 bis) ; à reconsidérer si l'application se met un
    # jour à garder une session ouverte plus longtemps (reprise différée
    # d'un très gros envoi, par exemple).
    try:
        _purger()
    except Exception:
        _log_journal.exception("purge après commit impossible")
    return bilan


class AbandonRequest(BaseModel):
    session: str


@app.post("/sync/abandon")
def sync_abandon(req: AbandonRequest, dev_id: str = Depends(require_device)) -> dict:
    """Supprime la session en cours sur ordre du téléphone (bouton « Interrompre »).

    Sans cette route, une synchro interrompue laissait son dossier de
    réception sur le NUC jusqu'à la prochaine purge de 24 h — potentiellement
    plusieurs gigaoctets d'une grosse vidéo à moitié envoyée. L'application
    appelle déjà cette route depuis le lot 1 bis ; elle recevait jusqu'ici un
    404 silencieux.
    """
    try:
        resultat = sessions.abandonner(config.INCOMING_DIR, req.session)
    except ValueError:
        raise HTTPException(status_code=400, detail="identifiant de session non autorisé")
    detail = f"session {req.session} : {resultat['supprimes']} fichier(s), {resultat['octets']} octets"
    _journaliser(lambda j: j.evenement("abandon", appareil=dev_id, detail=detail))
    return resultat


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
    resultat = devices().revoke(dev_id)
    _journaliser(lambda j: j.evenement(
        "revocation", appareil=dev_id, detail="demandée par le téléphone"))
    return {"retire": resultat}


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
    resultat = devices().revoke(device_id)
    _journaliser(lambda j: j.evenement(
        "revocation", appareil=device_id, detail="depuis l'administration"))
    return {"revoked": resultat}


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
        dev_id, _ = _appairage_en_cours
        _journaliser(lambda j: j.evenement("appairage", appareil=dev_id))


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


# --- pages d'historique (issue #30) -----------------------------------------
#
# Quatre pages, toutes derrière `require_admin` comme le reste de
# l'administration. `/historique/recherche` DOIT être déclarée avant
# `/historique/{identifiant}` : sinon FastAPI fait correspondre "recherche" à
# `identifiant` (un chemin paramétré capture tout ce qui suit, y compris un
# autre chemin fixe déclaré après lui).


@app.get("/historique", response_class=HTMLResponse)
def historique(_: None = Depends(require_admin)) -> str:
    """Liste des synchronisations, la plus récente d'abord."""
    return web.historique_html(journal().synchros())


@app.get("/historique/recherche", response_class=HTMLResponse)
def historique_recherche(q: str = "", _: None = Depends(require_admin)) -> str:
    """Recherche un fichier par nom (partiel) ou par empreinte exacte.

    Un `q` vide ou ne contenant que des espaces n'interroge PAS le journal :
    `Journal.rechercher("")` ramènerait la table entière (le motif LIKE
    devient "%%", qui correspond à tout). Seul le formulaire s'affiche alors.
    """
    q_utile = q.strip()
    resultats = journal().rechercher(q_utile) if q_utile else None
    return web.recherche_html(q, resultats)


@app.get("/historique/{identifiant}", response_class=HTMLResponse)
def historique_synchro(identifiant: str, _: None = Depends(require_admin)) -> str:
    """Détail d'une synchronisation : ses mouvements, origine vers destination."""
    s = journal().synchro(identifiant)
    if s is None:
        raise HTTPException(status_code=404, detail="synchronisation inconnue")
    return web.synchro_html(s, journal().mouvements(identifiant))


@app.get("/evenements", response_class=HTMLResponse)
def evenements(_: None = Depends(require_admin)) -> str:
    """Journal des faits ponctuels : démarrages, appairages, authentifications."""
    return web.evenements_html(journal().evenements())
