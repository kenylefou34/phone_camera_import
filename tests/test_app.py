import datetime, hashlib, importlib, io
from fastapi.testclient import TestClient
from mediaserve import web


def test_admin_html_contains_devices_and_pie():
    html = web.admin_html(
        devices=[{"id": "abc", "label": "Pixel", "paired_at": "2026-09-14"}],
        disk={"total": 1000, "utilise": 700, "libre": 300, "pourcentage_utilise": 70},
        media={"photos": 40000, "videos": 4669},
    )
    assert "Pixel" in html and "abc" in html
    assert "<svg" in html and "/pair" in html


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_DB", str(tmp_path / "cat.db"))
    monkeypatch.setenv("INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setenv("DEVICES_DB", str(tmp_path / "dev.db"))
    import mediaserve.config as c; importlib.reload(c)
    import mediaserve.app as a; importlib.reload(a)
    return a, TestClient(a.app)


def test_status_requires_auth(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    assert client.get("/status").status_code == 401


def test_status_with_token(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices.pair("test")
    r = client.get("/status", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_list_and_revoke_device(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices.pair("Pixel")
    assert any(d["id"] == dev_id for d in client.get("/devices").json())
    assert client.post(f"/devices/{dev_id}/revoke").status_code == 200
    assert client.get("/status", headers={"Authorization": f"Bearer {secret}"}).status_code == 401


def test_sync_flow_dedup_and_commit(tmp_path, monkeypatch):
    import mediasort.dates as d
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices.pair("Pixel"); h = {"Authorization": f"Bearer {secret}"}
    contenu = b"une vraie photo"; empreinte = hashlib.sha256(contenu).hexdigest()
    plan = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "Pictures/a.jpg", "size": len(contenu), "hash": empreinte}]})
    assert plan.status_code == 200
    session = plan.json()["session"]
    assert empreinte in plan.json()["needed"]
    up = client.post("/sync/upload", headers=h,
                     data={"session": session, "path": "Pictures/a.jpg"},
                     files={"file": ("a.jpg", io.BytesIO(contenu), "image/jpeg")})
    assert up.status_code == 200 and up.json()["hash"] == empreinte
    commit = client.post("/sync/commit", headers=h, json={"session": session})
    assert commit.status_code == 200
    assert commit.json()["sorted"] == 1 and commit.json()["photos"] == 1
    assert (tmp_path / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()
    plan2 = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "Pictures/a.jpg", "size": len(contenu), "hash": empreinte}]})
    assert empreinte not in plan2.json()["needed"]


def test_pair_page_creates_device_and_qr(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    avant = len(a.devices.list())
    r = client.get("/pair")
    assert r.status_code == 200 and "<svg" in r.text
    assert len(a.devices.list()) == avant + 1


def test_admin_page_renders(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200 and "mediaserve" in r.text
