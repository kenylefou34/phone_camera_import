"""Pages HTML du service : administration et appairage.

Tout est en ligne dans la page — aucune feuille de style ni police externe.
Le NUC doit rester utilisable sans accès à Internet, et le service ne sert
aucun fichier statique.

Les couleurs viennent d'une palette validée (contraste et daltonisme) : un
bleu unique pour la mesure, des gris pour le texte et les surfaces, et des
couleurs d'état réservées. Une couleur d'état ne porte jamais l'information
seule : elle est toujours doublée d'un mot.
"""

import html
from datetime import datetime

from . import stats

# --- jetons de couleur, thème clair puis sombre --------------------------
STYLE = """
:root {
  color-scheme: light;
  --plane:      #f9f9f7;   /* fond de page */
  --surface:    #fcfcfb;   /* cartes */
  --ink:        #0b0b0b;
  --ink-2:      #52514e;
  --muted:      #898781;
  --line:       #e1e0d9;
  --border:     rgba(11,11,11,0.10);
  --accent:     #2a78d6;
  --warning:    #fab219;
  --critical:   #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --plane:    #0d0d0d;
    --surface:  #1a1a19;
    --ink:      #ffffff;
    --ink-2:    #c3c2b7;
    --muted:    #898781;
    --line:     #2c2c2a;
    --border:   rgba(255,255,255,0.10);
    --accent:   #3987e5;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 16px 64px;
  background: var(--plane); color: var(--ink);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.page { max-width: 760px; margin: 0 auto; }
header { margin-bottom: 28px; }
h1 { margin: 0; font-size: 26px; letter-spacing: -0.015em; font-weight: 640; }
.hote { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
h2 {
  margin: 32px 0 12px; font-size: 12px; font-weight: 620;
  letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted);
}
.carte {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 14px; padding: 18px 20px;
}
.tuiles { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tuile .valeur {
  font-size: 30px; font-weight: 640; letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.tuile .libelle { color: var(--ink-2); font-size: 13px; margin-top: 2px; }
.large { grid-column: 1 / -1; }
.entete-jauge {
  display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
}
.piste {
  margin-top: 12px; height: 8px; border-radius: 4px;
  background: var(--line); overflow: hidden;
}
.remplissage { height: 100%; border-radius: 4px; background: var(--accent); }
.remplissage.warning  { background: var(--warning); }
.remplissage.critical { background: var(--critical); }
.detail { margin-top: 10px; color: var(--ink-2); font-size: 13px; }
.alerte { font-weight: 600; color: var(--ink); }
ul.appareils { list-style: none; margin: 0; padding: 0; }
ul.appareils li {
  display: flex; align-items: center; gap: 12px;
  padding: 13px 0; border-bottom: 1px solid var(--line);
}
ul.appareils li:last-child { border-bottom: 0; }
.nom { font-weight: 560; }
.quand { color: var(--muted); font-size: 12.5px; }
.etiquette {
  font-size: 11.5px; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--border); color: var(--ink-2); white-space: nowrap;
}
.pousse { margin-left: auto; }
.vide { color: var(--muted); padding: 13px 0; }
button, .bouton {
  font: inherit; font-size: 13.5px; cursor: pointer;
  border-radius: 9px; padding: 7px 13px;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink);
  text-decoration: none; display: inline-block;
}
button:hover, .bouton:hover { border-color: var(--muted); }
.bouton.principal {
  background: var(--accent); border-color: transparent; color: #fff; font-weight: 560;
}
code {
  font: 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--plane); border: 1px solid var(--border);
  border-radius: 7px; padding: 3px 7px; word-break: break-all;
}
@media (max-width: 520px) { .tuiles { grid-template-columns: 1fr; } }
"""

# Le QR est un tracé noir sur fond transparent : sans ce cadre blanc, il
# disparaîtrait en thème sombre. Le blanc est donc fixe, pas thémé.
STYLE_QR = """
.cadre-qr {
  background: #ffffff; border-radius: 16px; padding: 22px;
  display: inline-block; line-height: 0;
  border: 1px solid var(--border);
}
.centre { text-align: center; }
.centre .carte { display: inline-block; text-align: left; }
form { margin: 0 0 14px; display: flex; gap: 8px; align-items: center; }
input[type=date] {
  font: inherit; padding: 6px 10px; border-radius: 9px;
  border: 1px solid var(--border); background: var(--plane); color: var(--ink);
}
"""


# Abréviations écrites en dur : la locale française n'est pas garantie
# installée sur la machine, et on ne veut pas de mois en anglais.
_MOIS = ("janv.", "févr.", "mars", "avr.", "mai", "juin",
         "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def _date(horodatage: str) -> str:
    """« 2026-09-15T21:04:11 » -> « 15 sept. 2026 à 21:04 ».

    Une valeur inattendue est réaffichée telle quelle : mieux vaut une date
    bizarre qu'une page en erreur.
    """
    try:
        q = datetime.fromisoformat(horodatage)
    except (TypeError, ValueError):
        return str(horodatage)
    return f"{q.day} {_MOIS[q.month - 1]} {q.year} à {q.hour:02d}:{q.minute:02d}"


def _nombre(n: int) -> str:
    """12345 -> « 12 345 » (séparateur de milliers, lecture française)."""
    return f"{n:,}".replace(",", " ")


def _go(n: int) -> str:
    x = float(n)
    for unite in ("o", "Ko", "Mo", "Go", "To"):
        if x < 1024:
            return f"{x:.0f} {unite}"
        x /= 1024
    return f"{x:.0f} Po"


def _document(titre: str, corps: str, style_extra: str = "") -> str:
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{titre}</title><style>{STYLE}{style_extra}</style></head>"
        f'<body><div class="page">{corps}</div></body></html>'
    )


def _jauge_disque(disk: dict) -> str:
    """Jauge d'occupation : un ratio contre une limite se lit sur une jauge.

    Le niveau (ok / warning / critical) colore le remplissage ET ajoute un mot
    quand le disque se remplit — la couleur ne suffit jamais.
    """
    pct = disk["pourcentage_utilise"]
    niveau = stats.disk_level(pct)
    mot = {"warning": "Disque presque plein", "critical": "Disque presque plein"}.get(niveau)
    alerte = f' <span class="alerte">— {mot}</span>' if mot else ""
    return (
        '<div class="carte tuile large">'
        '<div class="entete-jauge">'
        f'<span class="valeur">{pct} %</span>'
        f'<span class="libelle">{_go(disk["libre"])} libres</span>'
        "</div>"
        f'<div class="piste"><div class="remplissage {niveau}" style="width:{pct}%"></div></div>'
        f'<div class="detail">{_go(disk["utilise"])} utilisés sur {_go(disk["total"])}{alerte}</div>'
        "</div>"
    )


def _bloc_apk(apk: dict | None) -> str:
    """Section « Application Android » de la page d'administration.

    Le cas « rien de déposé » a son propre texte, qui dit la commande à lancer.
    Une section vide, ou pire absente, laisserait croire que la fonction
    n'existe pas — alors qu'il manque seulement un envoi depuis la machine de
    compilation.
    """
    if apk is None:
        return (
            '<h2>Application Android</h2>'
            '<div class="carte"><p class="vide">Aucune application déposée '
            'sur ce serveur.</p>'
            '<p class="vide">Depuis la machine de compilation : '
            "<code>./deploy/envoyer-apk.sh</code></p></div>"
        )

    version = html.escape(str(apk.get("version") or "version inconnue"))
    code = apk.get("version_code")
    if code is not None:
        version += f" (code {html.escape(str(code))})"
    construit = apk.get("construit_le") or apk.get("depose_le")
    # L'empreinte complète est illisible et inutile à l'œil ; les douze
    # premiers caractères suffisent à comparer deux dépôts, et l'attribut
    # `title` garde la valeur entière pour qui veut la copier.
    sha = html.escape(str(apk.get("sha256") or ""))
    trace = (f'<p class="quand" title="{sha}">SHA-256 : {sha[:12]}…</p>'
             if sha else "")

    return (
        '<h2>Application Android</h2>'
        '<div class="carte">'
        f'<p><span class="nom">{version}</span></p>'
        f'<p class="quand">{_go(apk["octets"])} · déposée le '
        f"{_date(str(construit))}</p>"
        f"{trace}"
        '<p><a class="bouton principal" href="/apk">Télécharger l\'application'
        "</a></p>"
        '<p class="quand">Le téléphone doit autoriser l\'installation depuis '
        "cette source. Ouvrez cette page <em>depuis le téléphone</em>.</p>"
        "</div>"
    )


def _bloc_echecs(echecs: list | None) -> str:
    """Section « Médias non rangés » — ABSENTE quand tout va bien.

    En marche normale cette liste est vide, et un bloc « 0 média en échec »
    n'apprendrait rien tout en inquiétant. On ne l'affiche donc que s'il y a
    quelque chose à montrer — et alors il faut qu'il se voie.
    """
    if not echecs:
        return ""
    lignes = "".join(
        '<li><span class="nom">{fichier}</span>'
        '<span class="quand">{date}</span>'
        '<span class="etiquette">{raison}</span>'
        '<span class="pousse">{taille}</span></li>'.format(
            fichier=html.escape(e["fichier"]),
            date=_date(e.get("date", "")),
            raison=html.escape(e.get("raison", "")),
            taille=_go(e.get("octets", 0)),
        )
        for e in echecs
    )
    return (
        "<h2>Médias non rangés</h2>"
        '<div class="carte">'
        f"<p>{len(echecs)} média(s) reçus que le serveur n'a pas su ranger. "
        "Ils sont <strong>conservés</strong> sur le NUC : le téléphone peut "
        "les avoir supprimés de son côté. Videz seulement après avoir traité "
        "la cause.</p>"
        f"<ul class=\"liste\">{lignes}</ul>"
        "<p><button onclick=\"purger()\">Vider la quarantaine</button></p>"
        "</div>"
    )


def admin_html(devices: list, disk: dict, media: dict,
               apk: dict | None = None, echecs: list | None = None) -> str:
    """Page d'administration : chiffres clés, occupation disque, appareils.

    `apk` est facultatif : les appels historiques à trois arguments — et les
    tests qui les utilisent — continuent de fonctionner, la section
    « Application Android » affichant alors qu'aucun dépôt n'a eu lieu.
    """
    if devices:
        lignes = "".join(
            '<li><span class="nom">{label}</span>'
            '<span class="quand">{paired_at}</span>'
            "{attente}"
            '<span class="pousse"><button onclick="revoquer(\'{id}\')">Révoquer</button></span>'
            "</li>".format(
                label=d["label"], paired_at=_date(d["paired_at"]), id=d["id"],
                attente=('<span class="etiquette">en attente</span>'
                         if d.get("en_attente") else ""),
            )
            for d in devices
        )
    else:
        lignes = '<li class="vide">Aucun appareil appairé pour le moment.</li>'

    corps = (
        "<header><h1>phototheque</h1>"
        '<p class="hote">Service d\'ingestion des photos et vidéos</p></header>'
        "<h2>Bibliothèque</h2>"
        '<div class="tuiles">'
        f'<div class="carte tuile"><div class="valeur">{_nombre(media["photos"])}</div>'
        '<div class="libelle">photos</div></div>'
        f'<div class="carte tuile"><div class="valeur">{_nombre(media["videos"])}</div>'
        '<div class="libelle">vidéos</div></div>'
        f"{_jauge_disque(disk)}"
        "</div>"
        "<h2>Appareils appairés</h2>"
        f'<div class="carte"><ul class="appareils">{lignes}</ul></div>'
        '<h2>Ajouter un téléphone</h2>'
        '<a class="bouton principal" href="/pair">Afficher le QR d\'appairage</a>'
        f"{_bloc_apk(apk)}"
        f"{_bloc_echecs(echecs)}"
        "<script>"
        "function revoquer(id){"
        "if(!confirm('Révoquer cet appareil ?'))return;"
        "fetch('/devices/'+id+'/revoke',{method:'POST'}).then(()=>location.reload());}"
        "function purger(){"
        "if(!confirm('Supprimer definitivement ces medias du NUC ?'))return;"
        "fetch('/echecs/purge',{method:'POST'}).then(()=>location.reload());}"
        "</script>"
    )
    return _document("phototheque — admin", corps)


def pair_html(qr_svg: str, url: str, depuis: str) -> str:
    """Page d'appairage : le QR, l'adresse en secours, et la date de départ."""
    corps = (
        '<div class="centre">'
        "<header><h1>Appairer un téléphone</h1>"
        '<p class="hote">Scanne ce code avec l\'application</p></header>'
        f'<div class="cadre-qr">{qr_svg}</div>'
        '<div class="carte" style="margin-top:24px">'
        '<form method="post" action="/pair">'
        '<div class="detail">Importer les médias à partir du :</div>'
        f'<input type="date" name="depuis" value="{html.escape(depuis)}">'
        '<button type="submit">Enregistrer</button>'
        '</form>'
        f"<div class=\"detail\">Ou saisis l'adresse à la main :<br><code>{url}</code></div>"
        '<div class="detail" style="margin-top:10px;color:var(--muted)">'
        "Ce code reste valable 10 minutes. Il devient définitif dès que le "
        "téléphone s'en sert, et se renouvelle sinon.</div>"
        "</div>"
        '<p style="margin-top:24px"><a class="bouton" href="/">Retour</a></p>'
        "</div>"
    )
    return _document("phototheque — appairage", corps, STYLE_QR)
