from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    CHECKPOINT2_CORE_CSV,
    CONSOLIDATED_CHECKPOINT2_CSV,
    DISCOVERED_CSV,
    PRESS_CSV,
)
from .utils import clean_text, ensure_parent

# Checkpoint 2 has exactly these six columns. Review columns are appended only
# where a required field was backfilled from a secondary source, so the core
# schema stays identical to the checkpoint.
CORE_COLUMNS = [
    "movie_name",
    "release_year",
    "genre",
    "director",
    "revenue",
    "tickets_sold",
]
REVIEW_COLUMNS = [
    "to_review_director",
    "to_review_revenue",
]
OUTPUT_COLUMNS = CORE_COLUMNS + REVIEW_COLUMNS

# Directors were missing from every BoVN discovery row. These values were
# verified from the public Wikipedia infobox on 2026-11-19. The URL is kept in
# to_review_director so the source can be checked without re-crawling.
DIRECTOR_EVIDENCE: dict[str, tuple[str, str]] = {
    "Doraemon Movie 45 (2026): Nobita Và Lâu Đài Dưới Đáy Biển": (
        "Tetsuo Yajima",
        "https://en.wikipedia.org/wiki/Doraemon%3A_New_Nobita_and_the_Castle_of_the_Undersea_Devil",
    ),
    "Doraemon 2025: Nobita Và Cuộc Phiêu Lưu Vào Thế Giới Trong Tranh": (
        "Yukiyo Teramoto",
        "https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Art_World_Tales",
    ),
    "Phim Điện Ảnh Doraemon: Nobita Và Bản Giao Hưởng Địa Cầu": (
        "Kazuaki Imai",
        "https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Earth_Symphony",
    ),
    "Doraemon: Nobita Và Vùng Đất Lý Tưởng Trên Bầu Trời": (
        "Takumi Doyama",
        "https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Sky_Utopia",
    ),
    "Doraemon: Nobita Và Cuộc Chiến Vũ Trụ Tí Hon 2021": (
        "Susumu Yamaguchi",
        "https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Little_Star_Wars_2021",
    ),
    "Doraemon: Luôn Bên Bạn": (
        "Ryuichi Yagi, Takashi Yamazaki",
        "https://en.wikipedia.org/wiki/Stand_by_Me_Doraemon_2",
    ),
    "Doraemon: Nobita và Mặt Trăng Phiêu Lưu Ký": (
        "Shinnosuke Yakuwa",
        "https://en.wikipedia.org/wiki/Doraemon%3A_Nobita%27s_Chronicle_of_the_Moon_Exploration",
    ),
    "Conan Movie 28: Dư Ảnh Của Độc Nhãn": (
        "Katsuya Shigehara",
        "https://en.wikipedia.org/wiki/Detective_Conan%3A_One-eyed_Flashback",
    ),
    "Thanh Gươm Diệt Quỷ: Vô Hạn Thành": (
        "Haruo Sotozaki",
        "https://en.wikipedia.org/wiki/Demon_Slayer%3A_Kimetsu_no_Yaiba_%E2%80%93_The_Movie%3A_Infinity_Castle",
    ),
    "Phim Điện Ảnh Conan 27: Ngôi Sao 5 Cánh 1 Triệu Đô": (
        "Chika Nagaoka",
        "https://en.wikipedia.org/wiki/Detective_Conan%3A_The_Million-dollar_Pentagram",
    ),
}


def _text(value: Any) -> str:
    return clean_text(value) or ""


def _read_csv(path: Path | str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def _press_review(press_row: dict[str, Any] | None) -> str:
    if not press_row:
        return ""

    notes = ["needs_review"]
    display = _text(press_row.get("revenue_press_display"))
    if display:
        notes.append(f"press_display: {display}")
    basis = _text(press_row.get("revenue_press_basis"))
    if basis:
        notes.append(f"basis: {basis}")
    if str(press_row.get("revenue_press_is_lower_bound", "")).lower() == "true":
        notes.append("lower_bound: true")
    source = _text(press_row.get("source_url"))
    if source:
        notes.append(f"source: {source}")
    return " | ".join(notes)


def build_consolidated_csv(
    checkpoint_csv: Path | str | None = None,
    discovered_csv: Path | str | None = None,
    press_csv: Path | str | None = None,
    output_csv: Path | str | None = None,
) -> pd.DataFrame:
    """Merge checkpoint 2 with BoVN-discovered movies.

    Only movie_name, release_year, genre, director, revenue and tickets_sold
    are written to the core columns. Missing directors are filled from the
    verified Wikipedia infobox URLs above; missing revenue is filled with the
    press display text (never a reconstructed exact number) and flagged in
    to_review_revenue. Exact BoVN revenue always wins over press evidence.
    """
    checkpoint = _read_csv(checkpoint_csv or CHECKPOINT2_CORE_CSV)
    discovered = _read_csv(discovered_csv or DISCOVERED_CSV)
    press = _read_csv(press_csv or PRESS_CSV)

    press_by_name = {
        _text(row.get("movie_name")): row
        for row in press.to_dict("records")
        if _text(row.get("movie_name"))
    }
    checkpoint_names = {
        _text(row.get("movie_name"))
        for row in checkpoint.to_dict("records")
        if _text(row.get("movie_name"))
    }

    rows: list[dict[str, str]] = []
    for record in checkpoint.to_dict("records"):
        row = {column: _text(record.get(column)) for column in CORE_COLUMNS}
        row.update({column: "" for column in REVIEW_COLUMNS})
        rows.append(row)

    for record in discovered.to_dict("records"):
        name = _text(record.get("movie_name"))
        if not name or name in checkpoint_names:
            continue
        checkpoint_names.add(name)

        director_evidence = DIRECTOR_EVIDENCE.get(name)
        director = _text(record.get("director"))
        review_director = ""
        if not director and director_evidence:
            director, source_url = director_evidence
            review_director = f"wikipedia: {source_url}"

        revenue_bovn = _text(record.get("revenue_bovn"))
        press_row = press_by_name.get(name) if not revenue_bovn else None
        revenue = revenue_bovn or _text(press_row.get("revenue_press_display") if press_row else None)
        review_revenue = _press_review(press_row) if not revenue_bovn else ""

        rows.append(
            {
                "movie_name": name,
                "release_year": _text(record.get("release_year")),
                "genre": _text(record.get("genre")),
                "director": director,
                "revenue": revenue,
                "tickets_sold": _text(record.get("tickets_sold")),
                "to_review_director": review_director,
                "to_review_revenue": review_revenue,
            }
        )

    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    target = Path(output_csv or CONSOLIDATED_CHECKPOINT2_CSV)
    ensure_parent(target)
    frame.to_csv(target, index=False, encoding="utf-8-sig")
    return frame


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Merge checkpoint 2 with BoVN-discovered movies"
    )
    parser.add_argument("--checkpoint", default=str(CHECKPOINT2_CORE_CSV))
    parser.add_argument("--discovered", default=str(DISCOVERED_CSV))
    parser.add_argument("--press", default=str(PRESS_CSV))
    parser.add_argument("--output", default=str(CONSOLIDATED_CHECKPOINT2_CSV))
    args = parser.parse_args(argv)

    frame = build_consolidated_csv(
        checkpoint_csv=args.checkpoint,
        discovered_csv=args.discovered,
        press_csv=args.press,
        output_csv=args.output,
    )
    print(f"wrote {len(frame)} rows to {args.output}")


if __name__ == "__main__":
    main()
