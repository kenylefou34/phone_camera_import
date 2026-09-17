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
