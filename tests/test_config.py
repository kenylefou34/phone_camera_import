from mediasort import config


def test_month_folder_format():
    assert config.month_folder(5) == "05 MAI"
    assert config.month_folder(12) == "12 DECEMBRE"
    assert config.month_folder(1) == "01 JANVIER"


def test_extension_sets_are_lowercase_with_dot():
    assert ".jpg" in config.PHOTO_EXTS
    assert ".mp4" in config.VIDEO_EXTS
    assert config.PHOTO_EXTS.isdisjoint(config.VIDEO_EXTS)
