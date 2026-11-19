from movie_data_collector.press_revenue import (
    _build_queries,
    _choose,
    _extract_candidates,
    _norm_record,
    _specific_aliases,
    _specific_tokens,
    load_press_seed,
)
from movie_data_collector.search_tickets_web import SearchItem, _title_aliases


def _record():
    return {
        "movie_name": "Doraemon Movie 45 (2026): Nobita Và Lâu Đài Dưới Đáy Biển",
        "release_year": "2026",
        "release_date": "2026-05-22",
        "source_url_bovn": "https://v1.boxofficevietnam.com/movie/doraemon-movie-45-2026-nobita-va-lau-dai-duoi-day-bien/",
        "revenue_bovn": None,
    }


def test_build_queries():
    queries = _build_queries(_record(), 3)
    assert len(queries) == 3
    assert "doanh thu" in queries[0]
    # Query by subtitle, not by the franchise short title.
    assert "Lâu Đài Dưới Đáy Biển" in queries[1]


def test_extract_cumulative_revenue():
    aliases = _title_aliases(_record())
    item = SearchItem(
        title="Phim Doraemon Movie 45 lập kỷ lục tại phòng vé Việt",
        url="https://example.vn/doraemon-45",
        description="Sau một tháng công chiếu, Doraemon Movie 45: Nobita và lâu đài dưới đáy biển vượt mốc 200 tỷ đồng doanh thu tại rạp Việt.",
        published="Sat, 21 Jun 2026 18:42:11 GMT",
        source="example.vn",
        backend="bing",
        query='"Doraemon Movie 45" doanh thu',
    )
    cands = _extract_candidates(item, aliases, None)
    assert cands, "expected a revenue candidate"
    best, status = _choose(cands)
    assert best.revenue == 200_000_000_000
    assert best.is_lower_bound
    assert status in ("found", "needs_review")


def test_extract_rejects_foreign_revenue():
    aliases = _title_aliases(_record())
    item = SearchItem(
        title="Doraemon Movie 45 doanh thu Nhật Bản",
        url="https://example.vn/doraemon-jp",
        description="Doraemon Movie 45 đạt 4,26 tỷ Yên tại Nhật Bản, doanh thu toàn cầu 100 triệu USD.",
        published=None,
        source="example.vn",
        backend="bing",
        query='"Doraemon Movie 45" doanh thu',
    )
    assert _extract_candidates(item, aliases, None) == []


def test_norm_record_turns_nan_into_none():
    # pandas read_csv leaves float NaN for empty cells; NaN is truthy,
    # so without this an empty revenue_bovn would look present.
    assert _norm_record({"revenue_bovn": float("nan")}) == {"revenue_bovn": None}
    assert _norm_record({"revenue_bovn": "3,053,701,150"})["revenue_bovn"] == "3,053,701,150"


def test_load_press_seed():
    seed = load_press_seed("seeds/bovn_press_seed.json")
    assert len(seed) == 8
    for url, row in seed.items():
        assert row["revenue_press"] and row["revenue_press"] >= 48_000_000_000
        assert row["source_url"] and row["published"] and row["snippet"]
        assert row["source_url_bovn"] == url
    conan28 = seed["https://v1.boxofficevietnam.com/movie/conan-movie-28-du-anh-cua-doc-nhan/"]
    assert conan28["revenue_press"] == 174_000_000_000
    doraemon45 = seed["https://v1.boxofficevietnam.com/movie/doraemon-movie-45-2026-nobita-va-lau-dai-duoi-day-bien/"]
    assert doraemon45["revenue_press_is_lower_bound"] is True


def test_extract_penalises_opening_weekend():
    aliases = _title_aliases(_record())
    item = SearchItem(
        title="Doraemon Movie 45 mở màn 50 tỷ",
        url="https://example.vn/doraemon-opening",
        description="Doraemon Movie 45 thu 50 tỷ đồng trong tuần đầu ra rạp, cuối tuần mở màn ấn tượng.",
        published=None,
        source="example.vn",
        backend="bing",
        query='"Doraemon Movie 45" doanh thu',
    )
    cands = _extract_candidates(item, aliases, None)
    assert cands, "opening figure is still a candidate, just penalised"
    assert cands[0].period_cue is not None
    assert cands[0].score < 55.0


def test_extract_rejects_generic_franchise_match():
    # A Doraemon 43 (Bản Giao Hưởng) search must not accept a Doraemon 45
    # article just because both share the "Phim Điện Ảnh Doraemon" prefix.
    record = {
        "movie_name": "Phim Điện Ảnh Doraemon: Nobita Và Bản Giao Hưởng Địa Cầu",
        "release_year": "2024",
        "source_url_bovn": "https://v1.boxofficevietnam.com/movie/phim-dien-anh-doraemon-nobita-va-ban-giao-huong-dia-cau/",
        "revenue_bovn": None,
    }
    aliases = _title_aliases(record)
    specific = _specific_aliases(record)
    assert "phim dien anh doraemon" not in specific
    tokens = _specific_tokens(record)
    assert tokens == {"ban", "giao", "huong", "dia", "cau"}
    item = SearchItem(
        title="Báo động doanh thu phim có Quốc Trường và Ngọc Trinh",
        url="https://example.vn/bao-dong",
        description="Phần phim thứ 45 của phim điện ảnh Doraemon vừa chiếu sớm đã bỏ túi 37,5 tỷ. Trong khi đó, doanh thu phim có Quốc Trường và Ngọc Trinh rất thấp.",
        published=None,
        source="example.vn",
        backend="bing",
        query='"Phim Điện Ảnh Doraemon" doanh thu tỷ',
    )
    assert _extract_candidates(item, aliases, None, specific, tokens) == []


def test_extract_penalises_projection():
    aliases = _title_aliases(_record())
    specific = _specific_aliases(_record())
    tokens = _specific_tokens(_record())
    item = SearchItem(
        title="Doraemon Movie 45 chuẩn bị cán mốc 200 tỷ tại rạp Việt",
        url="https://example.vn/doraemon-45-chuan-bi",
        description="Doraemon Movie 45 chuẩn bị cán mốc 200 tỷ tại rạp Việt sau một tháng công chiếu.",
        published=None,
        source="example.vn",
        backend="google",
        query='"Nobita Và Lâu Đài Dưới Đáy Biển" doanh thu tỷ',
    )
    cands = _extract_candidates(item, aliases, None, specific, tokens)
    assert cands, "a pre-milestone figure is still a candidate, just penalised"
    assert cands[0].projection_cue is not None
    assert not cands[0].is_lower_bound
    _best, status = _choose(cands)
    assert status == "needs_review"
