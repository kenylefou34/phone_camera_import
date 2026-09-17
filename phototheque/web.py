"""Page HTML d'administration (appairage, appareils, stats disque)."""

from . import stats


def _go(n: int) -> str:
    x = float(n)
    for unite in ("o", "Ko", "Mo", "Go", "To"):
        if x < 1024:
            return f"{x:.0f} {unite}"
        x /= 1024
    return f"{x:.0f} Po"


def admin_html(devices: list, disk: dict, media: dict) -> str:
    """Rend la page d'admin : QR (lien), liste d'appareils + révocation, camembert."""
    lignes = "".join(
        f'<li>{d["label"]} <small>({d["paired_at"]})</small> '
        f'<button onclick="revoke(\'{d["id"]}\')">Révoquer</button></li>'
        for d in devices
    ) or "<li>Aucun appareil appairé</li>"
    pie = stats.pie_svg(disk["utilise"], disk["libre"])
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>phototheque — admin</title></head><body>
<h1>phototheque</h1>
<p><a href="/pair">➕ Appairer un nouveau téléphone (QR)</a></p>
<h2>Appareils appairés</h2><ul>{lignes}</ul>
<h2>Disque</h2>{pie}
<p>{_go(disk["utilise"])} utilisés / {_go(disk["total"])} — libre : {_go(disk["libre"])} ({100 - disk["pourcentage_utilise"]}%)</p>
<h2>Médias</h2><p>{media["photos"]} photos, {media["videos"]} vidéos</p>
<script>
function revoke(id){{fetch('/devices/'+id+'/revoke',{{method:'POST'}}).then(()=>location.reload());}}
</script></body></html>"""
