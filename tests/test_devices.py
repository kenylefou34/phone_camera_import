from phototheque.devices import DeviceStore


def test_pair_validate_revoke():
    st = DeviceStore(":memory:")
    dev_id, secret = st.pair("Pixel de Ken")
    assert st.validate(secret) == dev_id
    assert st.validate("mauvais") is None
    liste = st.list()
    assert len(liste) == 1 and liste[0]["label"] == "Pixel de Ken"
    assert st.revoke(dev_id) is True
    assert st.validate(secret) is None
    st.close()


def test_secret_not_stored_in_clear():
    st = DeviceStore(":memory:")
    _, secret = st.pair("x")
    rows = st._cx.execute("SELECT secret_hash FROM devices").fetchall()
    assert secret not in [r[0] for r in rows]
    st.close()


def _vieillir(store, device_id, minutes):
    """Recule la date d'appairage, pour tester l'expiration sans attendre."""
    from datetime import datetime, timedelta
    quand = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    store._cx.execute("UPDATE devices SET paired_at=? WHERE id=?", (quand, device_id))
    store._cx.commit()


def test_pair_creates_a_pending_device():
    """Un appairage fraîchement créé est EN ATTENTE tant qu'il n'a pas servi."""
    st = DeviceStore(":memory:")
    dev_id, _ = st.pair("Pixel")
    assert st.list()[0]["en_attente"] is True
    st.close()


def test_first_use_confirms_the_device():
    """Le premier usage valide confirme l'appareil : il ne peut plus expirer."""
    st = DeviceStore(":memory:")
    dev_id, secret = st.pair("Pixel")
    assert st.validate(secret) == dev_id
    assert st.list()[0]["en_attente"] is False
    st.close()


def test_pending_device_expires_if_never_used():
    """Un QR affiché puis jamais scanné ne doit pas rester valable indéfiniment."""
    st = DeviceStore(":memory:")
    dev_id, secret = st.pair("Pixel")
    _vieillir(st, dev_id, 11)          # délai par défaut : 10 minutes
    assert st.validate(secret) is None
    st.close()


def test_confirmed_device_does_not_expire():
    """Un téléphone réellement appairé reste valable, même des mois après."""
    st = DeviceStore(":memory:")
    dev_id, secret = st.pair("Pixel")
    st.validate(secret)                # confirmé par ce premier usage
    _vieillir(st, dev_id, 60 * 24 * 90)
    assert st.validate(secret) == dev_id
    st.close()


def test_purge_pending_removes_only_stale_unused_pairings():
    """Le ménage ne touche ni aux appairages récents ni aux appareils confirmés."""
    st = DeviceStore(":memory:")
    vieux, _ = st.pair("QR oublié")
    _vieillir(st, vieux, 11)
    recent, _ = st.pair("QR affiché à l'instant")
    confirme, secret = st.pair("Téléphone en service")
    st.validate(secret)
    _vieillir(st, confirme, 60 * 24)

    supprimes = st.purge_pending()

    assert supprimes == 1
    restants = {d["id"] for d in st.list()}
    assert restants == {recent, confirme}
    st.close()


def test_old_catalog_without_confirmed_column_keeps_working(tmp_path):
    """Migration : les appareils d'avant la colonne restent valables.

    On les considère confirmés — hors de question de déconnecter un téléphone
    qui fonctionne parce que le schéma a changé.
    """
    import sqlite3
    from phototheque.devices import _hash
    db = tmp_path / "ancien.db"
    cx = sqlite3.connect(str(db))
    cx.execute("CREATE TABLE devices (id TEXT PRIMARY KEY, label TEXT,"
               " secret_hash TEXT UNIQUE, paired_at TEXT)")
    cx.execute("INSERT INTO devices VALUES ('vieux','Pixel',?, '2026-01-01T10:00:00')",
               (_hash("secret-historique"),))
    cx.commit(); cx.close()

    st = DeviceStore(db)
    assert st.validate("secret-historique") == "vieux"
    assert st.list()[0]["en_attente"] is False
    assert st.purge_pending() == 0
    st.close()
