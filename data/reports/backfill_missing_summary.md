# Checkpoint 2 consolidation / missing-data summary

## Files

- Exact checkpoint 2 copy: `data/filtered/2020_2026_checkpoint2_core_no_original_title.csv`
- Final consolidated dataset: `data/filtered/2020_2026_checkpoint2_core_plus_bovn_discovery.csv`
- Raw discovery input: `data/data_dirty/bovn_discovered.csv`
- Raw press fallback input: `data/data_dirty/bovn_discovered_press.csv`
- Latest BoVN retry output: `data/bovn_discovered.csv`
- Press evidence output: `data/bovn_discovered_press.csv`

## Required fields

The final consolidated CSV has 79 rows (69 checkpoint rows + 10 discovered
rows). `movie_name`, `director`, and `revenue` are populated on every row.
No required value was invented.

Backfill applied:

- Reran `discover-bovn` with the existing seed queries. Exact BoVN revenue was
  recovered for `Doraemon: Nobita Và Cuộc Chiến Vũ Trụ Tí Hon 2021`
  (`48,754,730,731₫`), superseding the press lower bound of over 48 tỷ.
- Exact BoVN revenues were kept for `Doraemon: Luôn Bên Bạn`
  (`3,053,701,150₫`) and `Doraemon: Nobita và Mặt Trăng Phiêu Lưu Ký`
  (`25,455,000,000₫`).
- Seven rows still use press evidence because BoVN detail pages return 502.
  Their `revenue` values are the original press display text (for example
  `hơn 203,5 tỷ đồng`), not reconstructed exact VND totals.
- All 10 discovered rows were missing directors. Directors were filled from
  public Wikipedia infoboxes; each source URL is in `to_review_director`.

## Still needs human review

- 7 revenue rows are marked `needs_review` in `to_review_revenue`, with the
  press display text, basis, and article URL:
  - Doraemon Movie 45 (2026): Nobita Và Lâu Đài Dưới Đáy Biển
  - Doraemon 2025: Nobita Và Cuộc Phiêu Lưu Vào Thế Giới Trong Tranh
  - Phim Điện Ảnh Doraemon: Nobita Và Bản Giao Hưởng Địa Cầu
  - Doraemon: Nobita Và Vùng Đất Lý Tưởng Trên Bầu Trời
  - Conan Movie 28: Dư Ảnh Của Độc Nhãn
  - Thanh Gươm Diệt Quỷ: Vô Hạn Thành
  - Phim Điện Ảnh Conan 27: Ngôi Sao 5 Cánh 1 Triệu Đô
- 10 backfilled directors carry Wikipedia source URLs in `to_review_director`.

## Intentionally not backfilled

Per the task scope, no review or crawling was done for non-required fields:

- `release_year` is empty for `Doraemon: Nobita Và Vùng Đất Lý Tưởng Trên Bầu Trời`
  and `Phim Điện Ảnh Conan 27: Ngôi Sao 5 Cánh 1 Triệu Đô`.
- `genre` is empty for all discovered rows.
- `tickets_sold` is empty for all discovered rows.
- One discovered title, `Doraemon: Nobita và Mặt Trăng Phiêu Lưu Ký`, is from
  2019. It is retained as-is because no year filter was requested.
