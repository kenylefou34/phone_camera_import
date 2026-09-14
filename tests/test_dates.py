import datetime
from mediasort import dates


def test_date_from_filename_patterns():
    d = datetime.date(2023, 5, 26)
    assert dates.date_from_filename("IMG_20230526_101500.jpg") == d
    assert dates.date_from_filename("VID-20230526-WA0009.mp4") == d
    assert dates.date_from_filename("PXL_20230526_101500123.jpg") == d
    assert dates.date_from_filename("Screenshot_2023-05-26-10-15.png") == d
    assert dates.date_from_filename("signal-2023-05-26-101500.jpg") == d


def test_date_from_filename_none_when_absent():
    assert dates.date_from_filename("photo_sans_date.jpg") is None


def test_date_from_filename_rejects_impossible_dates():
    # 2023-13-40 n'est pas une date valide -> None
    assert dates.date_from_filename("IMG_20231340.jpg") is None
