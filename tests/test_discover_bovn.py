from movie_data_collector.discover_bovn import parse_release_date, query_matches


def test_parse_dmy():
    assert parse_release_date("Doraemon Movie 45 (2026): Nobita 22/05/2026") == (
        "2026-05-22",
        "2026",
    )


def test_parse_ymd():
    assert parse_release_date("Phim Điện Ảnh Doraemon 2024-05-18") == (
        "2024-05-18",
        "2024",
    )


def test_parse_year_only():
    assert parse_release_date("Conan Movie 28 (2025)") == (None, "2025")


def test_parse_none():
    assert parse_release_date(None) == (None, None)
    assert parse_release_date("no date here") == (None, None)


def test_query_matches_anime():
    assert query_matches("Doraemon", "Doraemon Movie 45 (2026): Nobita")
    assert query_matches("Vô Hạn Thành", "Thanh Gươm Diệt Quỷ: Vô Hạn Thành")
    assert query_matches("Conan Movie 28", "Conan Movie 28: Dư Ảnh Của Độc Nhãn")
    assert query_matches("Doraemon 2025", "Doraemon 2025: Nobita Và Cuộc Phiêu Lưu")


def test_query_matches_rejects_sidebar_noise():
    # Unrelated movies that appear on BoVN search pages (latest / sidebar).
    assert not query_matches("Vô Hạn Thành", "Trại Giam Hạnh Phúc")
    assert not query_matches("Vô Hạn Thành", "Khi Thần Chết Đổ Chuông")
    assert not query_matches("Doraemon 2025", "Doraemon Movie 45 (2026): Nobita")
    assert not query_matches("Doraemon", "Conan Movie 28: Dư Ảnh Của Độc Nhãn")
