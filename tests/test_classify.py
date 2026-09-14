import datetime
import pathlib
from mediasort import classify
from mediasort.dates import DateResult


def test_media_type():
    assert classify.media_type(".JPG") == "photo"
    assert classify.media_type(".mp4") == "video"
    assert classify.media_type(".txt") is None


def test_is_whatsapp_and_excluded():
    assert classify.is_whatsapp(pathlib.Path("/x/WhatsApp Images/IMG.jpg")) is True
    assert classify.is_whatsapp(pathlib.Path("/x/Camera/IMG.jpg")) is False
    assert classify.is_excluded(pathlib.Path("/x/WhatsApp/Sent/IMG.jpg")) is True
    assert classify.is_excluded(pathlib.Path("/x/WhatsApp Images/IMG.jpg")) is False


def test_is_curated_folder():
    assert classify.is_curated_folder("2023") is False
    assert classify.is_curated_folder("05 MAI") is False
    assert classify.is_curated_folder("Bapteme Paula") is True
    assert classify.is_curated_folder("02 - CANARIAS") is True


def test_destination_photo():
    lib = pathlib.Path("/lib")
    src = pathlib.Path("/src/Camera/IMG_20230526.jpg")
    dr = DateResult(datetime.date(2023, 5, 26), "metadata")
    assert classify.destination(lib, src, dr, "photo") == \
        pathlib.Path("/lib/Photos/2023/05 MAI/IMG_20230526.jpg")


def test_destination_whatsapp_video():
    lib = pathlib.Path("/lib")
    src = pathlib.Path("/src/WhatsApp Video/VID-20230526-WA0009.mp4")
    dr = DateResult(datetime.date(2023, 5, 26), "filename")
    assert classify.destination(lib, src, dr, "video") == \
        pathlib.Path("/lib/WhatsApp/Videos/2023/05 MAI/VID-20230526-WA0009.mp4")


def test_destination_unknown_goes_to_triage():
    lib = pathlib.Path("/lib")
    src = pathlib.Path("/src/Camera/mystere.jpg")
    dr = DateResult(None, "unknown")
    assert classify.destination(lib, src, dr, "photo") == \
        pathlib.Path("/lib/_A_TRIER/mystere.jpg")
