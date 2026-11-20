from __future__ import annotations

import csv
import hashlib
import html
import io
import re
import textwrap
from collections import Counter
from decimal import Decimal, getcontext
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import plotly.graph_objects as go
from matplotlib.patches import FancyBboxPatch
from plotly.io import to_html

getcontext().prec = 60

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "processed" / "checkpoint3.csv"
PLOTLY_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "reports" / "checkpoint3_visualizations"
CSS_PATH = PLOTLY_DIR / "assets" / "css" / "style.css"
HTML_PATH = PLOTLY_DIR / "index.html"

EXPECTED_COLUMNS = [
    "movie_name",
    "release_year",
    "genre",
    "director",
    "revenue",
    "tickets_sold",
]

CAVEAT = (
    "Ticket counts are estimated/recorded values and have not been independently verified."
)
CAVEAT_VI = (
    "Lưu ý: tickets_sold là hỗn hợp giá trị gốc, ước tính và giá trị nhập thủ công; "
    "không phải số vé đã xác minh độc lập."
)

BOM = b"\xef\xbb\xbf"
MISSING_MARKERS = {"n/a", "na", "null", "none", "-", "--", "nan", "?", "missing"}

PRIMARY = "#2563eb"
TEAL = "#0f766e"
AMBER = "#b45309"
SLATE = "#243b53"
GRID = "#e2e8f0"
PANEL = "#f8fafc"
INK = "#102a43"
MUTED = "#486581"

PLOTLY_CONFIG = {
    "responsive": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

STATIC_FILES = [
    "01_dataset_overview.png",
    "02_movies_by_year.png",
    "03_revenue_by_year.png",
    "04_top10_revenue.png",
    "05_top10_tickets.png",
    "06_tickets_by_year.png",
    "07_genre_distribution.png",
    "08_top10_directors.png",
    "09_revenue_vs_tickets.png",
    "10_avg_revenue_per_ticket.png",
]

CHART_IDS = [
    "chart-overview",
    "chart-year-counts",
    "chart-revenue-by-year",
    "chart-top-revenue",
    "chart-top-tickets",
    "chart-tickets-by-year",
    "chart-genres",
    "chart-directors",
    "chart-revenue-tickets",
    "chart-avg-revenue-ticket",
]

CSS = """:root {
  --bg: #eef2f7;
  --panel: #ffffff;
  --panel-soft: #f8fafc;
  --ink: #102a43;
  --muted: #486581;
  --line: #d9e2ec;
  --blue: #2563eb;
  --teal: #0f766e;
  --amber: #b45309;
  --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
  --radius: 16px;
}

* { box-sizing: border-box; }

html { scroll-behavior: smooth; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}

.page-shell {
  width: min(1440px, calc(100% - 40px));
  margin: 0 auto;
  padding: 44px 0 64px;
}

.hero {
  padding: 34px 38px;
  border-radius: 22px;
  background: linear-gradient(135deg, #102a43 0%, #1d4ed8 100%);
  color: #f8fafc;
  box-shadow: var(--shadow);
}

.hero__eyebrow {
  margin: 0 0 10px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #bfdbfe;
}

.hero h1 {
  margin: 0;
  font-size: clamp(1.8rem, 3vw, 3rem);
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.hero__lede {
  max-width: 900px;
  margin: 16px 0 0;
  font-size: 1rem;
  color: #dbeafe;
}

.notice {
  margin: 24px 0;
  padding: 18px 22px;
  border-left: 5px solid var(--amber);
  border-radius: 12px;
  background: #fffbeb;
  color: #78350f;
  box-shadow: var(--shadow);
}

.notice strong { color: #7c2d12; }

code {
  padding: 1px 5px;
  border-radius: 5px;
  background: rgba(15, 23, 42, 0.07);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.9em;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
  margin-bottom: 24px;
}

.metric {
  position: relative;
  overflow: hidden;
  padding: 18px 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--panel);
  box-shadow: var(--shadow);
}

.metric::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 5px;
  background: var(--blue);
}

.metric--teal::before { background: var(--teal); }
.metric--amber::before { background: var(--amber); }

.metric__label {
  margin: 0 0 6px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}

.metric__value {
  margin: 0;
  font-size: clamp(1.2rem, 1.8vw, 1.8rem);
  font-weight: 750;
  line-height: 1.2;
}

.metric__note {
  margin: 7px 0 0;
  font-size: 0.8rem;
  color: var(--muted);
}

.charts { display: grid; gap: 22px; }

.chart-card {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--panel);
  box-shadow: var(--shadow);
}

.chart-card__header {
  padding: 22px 26px 12px;
  border-bottom: 1px solid #edf2f7;
}

.chart-card__header h2 {
  margin: 0;
  font-size: 1.2rem;
}

.chart-card__header p {
  margin: 6px 0 0;
  font-size: 0.9rem;
  color: var(--muted);
}

.chart-card__plot { padding: 6px 12px 12px; }

.chart-card__plot .js-plotly-plot,
.chart-card__plot .plot-container,
.chart-card__plot .svg-container {
  width: 100% !important;
}

.method {
  margin-top: 26px;
  padding: 26px 28px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--panel);
  box-shadow: var(--shadow);
}

.method h2 { margin: 0 0 18px; font-size: 1.3rem; }

.method__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 28px;
}

.method h3 { margin: 0 0 6px; font-size: 1rem; }
.method p { margin: 0; font-size: 0.9rem; color: var(--muted); }

.footer {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 0.82rem;
  text-align: center;
}

.footer p { margin: 0; }

@media (max-width: 1080px) {
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  .page-shell { width: min(100% - 24px, 1440px); padding-top: 24px; }
  .hero { padding: 26px 22px; }
  .metrics { grid-template-columns: 1fr; }
  .method__grid { grid-template-columns: 1fr; }
  .chart-card__header { padding: 18px 18px 10px; }
  .chart-card__plot { padding: 4px 6px 8px; }
}
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_manifest(paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for base in paths:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                result[path.as_posix()] = sha256_bytes(path.read_bytes())
    return result


def parse_revenue(value: str) -> Decimal:
    value = value.strip()
    exact = re.fullmatch(r"\d{1,3}(?:,\d{3})+₫", value)
    if exact:
        return Decimal(value[:-1].replace(",", ""))
    billions = re.fullmatch(
        r"(\d+(?:\.\d{3})*|\d+)(?:,(\d+))?\s*tỷ(?:\s*đồng)?",
        value,
        re.IGNORECASE,
    )
    if billions:
        whole = billions.group(1).replace(".", "")
        fraction = billions.group(2) or ""
        number = Decimal(whole + ("." + fraction if fraction else ""))
        return number * Decimal(1_000_000_000)
    raise ValueError(f"Cannot parse revenue safely: {value!r}")


def parse_tickets(value: str) -> int:
    value = value.strip()
    if not re.fullmatch(r"\d+", value):
        raise ValueError(f"Cannot parse tickets_sold safely: {value!r}")
    number = int(value)
    if number <= 0:
        raise ValueError(f"tickets_sold must be positive: {value!r}")
    return number


def split_genres(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;|/]+", value) if part.strip()]


def load_data() -> tuple[list[dict[str, object]], str]:
    raw = CSV_PATH.read_bytes()
    if not raw.startswith(BOM):
        raise ValueError("checkpoint3.csv must be UTF-8 with BOM")
    text = raw[3:].decode("utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows or rows[0] != EXPECTED_COLUMNS:
        raise ValueError(f"Unexpected header: {rows[0] if rows else None}")
    data_rows = rows[1:]
    if len(data_rows) != 78:
        raise ValueError(f"Expected 78 rows, found {len(data_rows)}")

    records: list[dict[str, object]] = []
    for line_number, row in enumerate(data_rows, start=2):
        if len(row) != len(EXPECTED_COLUMNS):
            raise ValueError(f"Line {line_number}: expected 6 fields, found {len(row)}")
        record = dict(zip(EXPECTED_COLUMNS, row))
        for column, value in record.items():
            stripped = value.strip()
            if not stripped or stripped.casefold() in MISSING_MARKERS:
                raise ValueError(f"Line {line_number}: missing value in {column}")
        if not re.fullmatch(r"\d{4}", record["release_year"]):
            raise ValueError(f"Line {line_number}: invalid release_year {record['release_year']!r}")
        year = int(record["release_year"])
        if not 2020 <= year <= 2026:
            raise ValueError(f"Line {line_number}: release_year outside 2020-2026: {year}")

        revenue = parse_revenue(record["revenue"])
        tickets = parse_tickets(record["tickets_sold"])
        director = record["director"].strip() or "(Không rõ)"
        records.append(
            {
                **record,
                "_year": year,
                "_revenue": revenue,
                "_tickets": tickets,
                "_director": director,
                "_line": line_number,
            }
        )

    names = [str(record["movie_name"]) for record in records]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate movie_name values found")
    return records, sha256_bytes(raw)


def to_billions(value: Decimal) -> Decimal:
    return value / Decimal(1_000_000_000)


def fmt_int(value: int | Decimal) -> str:
    return f"{int(value):,}".replace(",", ".")


def fmt_vnd(value: Decimal) -> str:
    return f"{fmt_int(value)}₫"


def fmt_ty(value: Decimal) -> str:
    formatted = f"{to_billions(value):,.2f}"
    formatted = formatted.replace(",", "_NGHIN_").replace(".", ",").replace("_NGHIN_", ".")
    return formatted + " tỷ"


def fmt_ratio(value: Decimal) -> str:
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "_NGHIN_").replace(".", ",").replace("_NGHIN_", ".")
    return formatted + " VND/vé"


def wrap_label(value: str, width: int = 42) -> str:
    return "\n".join(
        textwrap.wrap(value, width=width, break_long_words=False, break_on_hyphens=False)
    )


def aggregate(records: list[dict[str, object]]) -> dict[str, object]:
    years = sorted({int(record["_year"]) for record in records})
    year_stats = []
    for year in years:
        subset = [record for record in records if record["_year"] == year]
        year_stats.append(
            {
                "year": year,
                "movies": len(subset),
                "revenue": sum((record["_revenue"] for record in subset), Decimal(0)),
                "tickets": sum(int(record["_tickets"]) for record in subset),
            }
        )

    top_revenue = sorted(
        records,
        key=lambda record: (-record["_revenue"], str(record["movie_name"])),
    )[:10]
    top_tickets = sorted(
        records,
        key=lambda record: (-record["_tickets"], str(record["movie_name"])),
    )[:10]

    genre_counter: Counter[str] = Counter()
    for record in records:
        genre_counter.update(split_genres(str(record["genre"])))
    genres = sorted(genre_counter.items(), key=lambda item: (-item[1], item[0]))

    director_counter: Counter[str] = Counter(str(record["_director"]) for record in records)
    directors = sorted(director_counter.items(), key=lambda item: (-item[1], item[0]))[:10]

    total_revenue = sum((record["_revenue"] for record in records), Decimal(0))
    total_tickets = sum(int(record["_tickets"]) for record in records)
    return {
        "rows": len(records),
        "year_min": min(years),
        "year_max": max(years),
        "year_stats": year_stats,
        "top_revenue": top_revenue,
        "top_tickets": top_tickets,
        "genres": genres,
        "directors": directors,
        "total_revenue": total_revenue,
        "total_tickets": total_tickets,
        "avg_revenue": total_revenue / Decimal(len(records)),
        "avg_tickets": Decimal(total_tickets) / Decimal(len(records)),
        "avg_revenue_per_ticket": total_revenue / Decimal(total_tickets),
        "missing_directors": sum(
            1 for record in records if str(record["director"]).strip() == ""
        ),
        "revenue_parsed": len(records),
    }


def configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#d0d7de",
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "text.color": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linestyle": "-",
            "grid.linewidth": 0.8,
            "font.family": "DejaVu Sans",
            "font.sans-serif": ["DejaVu Sans"],
            "axes.unicode_minus": False,
            "font.size": 10,
            "axes.titlesize": 14,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "figure.dpi": 180,
            "savefig.dpi": 180,
        }
    )


def style_axes(ax: plt.Axes, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, fontweight="bold", pad=14)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def add_footnote(fig: plt.Figure, text: str) -> None:
    fig.text(0.012, 0.012, text, fontsize=7.5, color=MUTED, wrap=True)


def save_static(fig: plt.Figure, filename: str) -> None:
    fig.savefig(STATIC_DIR / filename, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def build_static_charts(
    records: list[dict[str, object]], stats: dict[str, object]
) -> list[str]:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()
    written: list[str] = []

    # 01 Dataset overview
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.axis("off")
    fig.suptitle(
        "Tổng quan tập dữ liệu phim 2020–2026 (78 phim)",
        fontsize=18,
        fontweight="bold",
        x=0.02,
        ha="left",
        y=0.96,
    )
    metrics = [
        ("Tổng số phim", fmt_int(stats["rows"]), "78 phim sau khi loại bỏ năm 2019"),
        (
            "Phạm vi năm",
            f"{stats['year_min']}–{stats['year_max']}",
            "Năm phát hành hợp lệ",
        ),
        ("Tổng doanh thu", fmt_ty(stats["total_revenue"]), f"{fmt_vnd(stats['total_revenue'])}"),
        (
            "Tổng số vé",
            fmt_int(stats["total_tickets"]),
            "Giá trị gốc / ước tính / nhập thủ công",
        ),
        (
            "Trung bình doanh thu/phim",
            fmt_ty(stats["avg_revenue"]),
            "Tổng doanh thu chia cho 78 phim",
        ),
        (
            "Trung bình vé/phim",
            f"{stats['avg_tickets']:,.0f}".replace(",", "."),
            "Tổng số vé chia cho 78 phim",
        ),
    ]
    colors = ["#dbeafe", "#ccfbf1", "#fef3c7"]
    for index, (label, value, note) in enumerate(metrics):
        row, col = divmod(index, 3)
        x = 0.02 + col * 0.33
        y = 0.70 - row * 0.34
        box = FancyBboxPatch(
            (x, y),
            0.30,
            0.27,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            linewidth=0.8,
            edgecolor="#cbd5e1",
            facecolor=colors[col],
            transform=ax.transAxes,
        )
        ax.add_patch(box)
        ax.text(x + 0.02, y + 0.20, label, transform=ax.transAxes, fontsize=10, color=MUTED, weight="bold")
        ax.text(x + 0.02, y + 0.12, value, transform=ax.transAxes, fontsize=18, color=INK, weight="bold")
        ax.text(x + 0.02, y + 0.045, note, transform=ax.transAxes, fontsize=8, color=MUTED)
    add_footnote(fig, CAVEAT)
    fig.subplots_adjust(bottom=0.08, top=0.90)
    save_static(fig, STATIC_FILES[0])
    written.append(STATIC_FILES[0])

    year_stats = stats["year_stats"]
    years = [item["year"] for item in year_stats]

    # 02 Movies by year
    fig, ax = plt.subplots(figsize=(11, 6))
    counts = [int(item["movies"]) for item in year_stats]
    bars = ax.bar([str(year) for year in years], counts, color=PRIMARY)
    ax.bar_label(bars, [fmt_int(value) for value in counts], padding=3)
    ax.set_ylim(0, max(counts) * 1.18)
    style_axes(ax, "Số lượng phim theo năm phát hành", "Năm phát hành", "Số phim")
    add_footnote(fig, "Nguồn: data/processed/checkpoint3.csv")
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    save_static(fig, STATIC_FILES[1])
    written.append(STATIC_FILES[1])

    # 03 Revenue by year
    fig, ax = plt.subplots(figsize=(11, 6))
    revenues = [float(to_billions(item["revenue"])) for item in year_stats]
    bars = ax.bar([str(year) for year in years], revenues, color=TEAL)
    ax.bar_label(bars, [fmt_ty(item["revenue"]) for item in year_stats], padding=3, fontsize=8)
    ax.set_ylim(0, max(revenues) * 1.18)
    style_axes(ax, "Tổng doanh thu theo năm phát hành", "Năm phát hành", "Doanh thu (tỷ VND)")
    add_footnote(fig, "Đơn vị hiển thị: tỷ VND; giá trị gốc trong CSV không bị thay đổi.")
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    save_static(fig, STATIC_FILES[2])
    written.append(STATIC_FILES[2])

    # 04 Top 10 revenue
    fig, ax = plt.subplots(figsize=(13, 9))
    top_revenue = list(stats["top_revenue"])
    labels = [wrap_label(str(record["movie_name"])) for record in top_revenue]
    values = [float(to_billions(record["_revenue"])) for record in top_revenue]
    ax.barh(labels, values, color=TEAL)
    ax.invert_yaxis()
    for index, record in enumerate(top_revenue):
        ax.text(
            float(to_billions(record["_revenue"])),
            index,
            " " + fmt_ty(record["_revenue"]),
            va="center",
            fontsize=8,
        )
    ax.set_xlim(0, max(values) * 1.20)
    style_axes(ax, "Top 10 phim theo doanh thu", "Doanh thu (tỷ VND)", "Phim")
    fig.subplots_adjust(left=0.36, bottom=0.10, top=0.93)
    add_footnote(fig, "Xếp hạng giảm dần theo doanh thu; đơn vị tỷ VND.")
    save_static(fig, STATIC_FILES[3])
    written.append(STATIC_FILES[3])

    # 05 Top 10 tickets
    fig, ax = plt.subplots(figsize=(13, 9))
    top_tickets = list(stats["top_tickets"])
    labels = [wrap_label(str(record["movie_name"])) for record in top_tickets]
    values = [int(record["_tickets"]) for record in top_tickets]
    ax.barh(labels, values, color=AMBER)
    ax.invert_yaxis()
    for index, record in enumerate(top_tickets):
        ax.text(int(record["_tickets"]), index, " " + fmt_int(record["_tickets"]), va="center", fontsize=8)
    ax.set_xlim(0, max(values) * 1.20)
    style_axes(ax, "Top 10 phim theo tickets_sold", "Số vé (giá trị gốc / ước tính / nhập thủ công)", "Phim")
    fig.subplots_adjust(left=0.36, bottom=0.10, top=0.93)
    add_footnote(fig, CAVEAT)
    save_static(fig, STATIC_FILES[4])
    written.append(STATIC_FILES[4])

    # 06 Tickets by year
    fig, ax = plt.subplots(figsize=(11, 6))
    tickets = [int(item["tickets"]) for item in year_stats]
    bars = ax.bar([str(year) for year in years], tickets, color=AMBER)
    ax.bar_label(bars, [fmt_int(value) for value in tickets], padding=3, fontsize=8)
    ax.set_ylim(0, max(tickets) * 1.18)
    style_axes(ax, "Tổng số vé theo năm phát hành", "Năm phát hành", "Tổng số vé")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    add_footnote(fig, CAVEAT)
    save_static(fig, STATIC_FILES[5])
    written.append(STATIC_FILES[5])

    # 07 Genre distribution
    fig, ax = plt.subplots(figsize=(12, max(8, 0.42 * len(stats["genres"]))))
    genres = list(stats["genres"])
    labels = [wrap_label(name, 30) for name, _ in genres]
    counts = [count for _, count in genres]
    ax.barh(labels, counts, color=PRIMARY)
    ax.invert_yaxis()
    ax.bar_label(ax.containers[0], padding=3, fontsize=8)
    ax.set_xlim(0, max(counts) * 1.16)
    style_axes(ax, "Số phim theo thể loại", "Số phim", "Thể loại")
    fig.subplots_adjust(left=0.30, bottom=0.10, top=0.93)
    add_footnote(fig, "Trường genre ghép được tách theo dấu phẩy, chấm phẩy, gạch đứng hoặc gạch chéo.")
    save_static(fig, STATIC_FILES[6])
    written.append(STATIC_FILES[6])

    # 08 Top 10 directors
    fig, ax = plt.subplots(figsize=(12, 8))
    directors = list(stats["directors"])
    labels = [wrap_label(name, 30) for name, _ in directors]
    counts = [count for _, count in directors]
    ax.barh(labels, counts, color=PRIMARY)
    ax.invert_yaxis()
    ax.bar_label(ax.containers[0], padding=3, fontsize=8)
    ax.set_xlim(0, max(counts) * 1.16)
    style_axes(ax, "Top 10 đạo diễn theo số phim", "Số phim", "Đạo diễn")
    fig.subplots_adjust(left=0.30, bottom=0.10, top=0.93)
    missing_note = (
        f"Giá trị đạo diễn thiếu: {stats['missing_directors']}; không gán tên giả."
    )
    add_footnote(fig, missing_note)
    save_static(fig, STATIC_FILES[7])
    written.append(STATIC_FILES[7])

    # 09 Revenue vs tickets
    fig, ax = plt.subplots(figsize=(11, 7))
    scatter_x = [float(to_billions(record["_revenue"])) for record in records]
    scatter_y = [int(record["_tickets"]) for record in records]
    scatter_years = [int(record["_year"]) for record in records]
    scatter = ax.scatter(scatter_x, scatter_y, c=scatter_years, cmap="viridis", s=38, alpha=0.85, edgecolors="white", linewidths=0.4)
    colorbar = fig.colorbar(scatter, ax=ax)
    colorbar.set_label("Năm phát hành")
    style_axes(ax, "Doanh thu so với số vé", "Doanh thu (tỷ VND)", "Số vé")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    add_footnote(fig, CAVEAT)
    save_static(fig, STATIC_FILES[8])
    written.append(STATIC_FILES[8])

    # 10 Average revenue per ticket
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.axis("off")
    ratio = fmt_ratio(stats["avg_revenue_per_ticket"])
    ax.text(0.5, 0.62, ratio, ha="center", va="center", fontsize=30, fontweight="bold", color=TEAL, transform=ax.transAxes)
    ax.text(
        0.5,
        0.43,
        "Tổng doanh thu / tổng tickets_sold (78 phim)",
        ha="center",
        va="center",
        fontsize=12,
        color=MUTED,
        transform=ax.transAxes,
    )
    ax.text(
        0.5,
        0.30,
        f"{fmt_vnd(stats['total_revenue'])} / {fmt_int(stats['total_tickets'])} vé",
        ha="center",
        va="center",
        fontsize=11,
        color=INK,
        transform=ax.transAxes,
    )
    fig.suptitle(
        "Doanh thu trung bình trên mỗi vé ước tính/đã ghi nhận",
        fontsize=16,
        fontweight="bold",
        x=0.02,
        ha="left",
        y=0.94,
    )
    add_footnote(fig, "Tỷ lệ này không phải giá vé được xác minh độc lập. " + CAVEAT)
    fig.subplots_adjust(bottom=0.10, top=0.86)
    save_static(fig, STATIC_FILES[9])
    written.append(STATIC_FILES[9])

    return written


def plotly_layout(
    fig: go.Figure,
    title: str,
    x_title: str,
    y_title: str,
    height: int = 520,
    margin_left: int = 80,
) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.02, xanchor="left", font=dict(size=18, color=INK)),
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor=PANEL,
        font=dict(family="Segoe UI, Roboto, Helvetica, Arial, sans-serif", size=13, color=SLATE),
        height=height,
        margin=dict(l=margin_left, r=36, t=78, b=64),
        hoverlabel=dict(bgcolor="#0f172a", font_color="white"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(title_text=x_title, gridcolor=GRID, zeroline=False)
    fig.update_yaxes(title_text=y_title, gridcolor=GRID, zeroline=False)
    return fig


def build_plotly_charts(
    records: list[dict[str, object]], stats: dict[str, object]
) -> list[tuple[str, str, str, go.Figure]]:
    charts: list[tuple[str, str, str, go.Figure]] = []
    year_stats = stats["year_stats"]
    years = [item["year"] for item in year_stats]

    labels = [
        "Tổng số phim",
        "Phạm vi năm",
        "Tổng doanh thu",
        "Tổng số vé",
        "Doanh thu trung bình/phim",
        "Số vé trung bình/phim",
        "Doanh thu/vé",
    ]
    values = [
        fmt_int(stats["rows"]),
        f"{stats['year_min']}–{stats['year_max']}",
        fmt_ty(stats["total_revenue"]),
        fmt_int(stats["total_tickets"]),
        fmt_ty(stats["avg_revenue"]),
        f"{stats['avg_tickets']:,.0f}".replace(",", "."),
        fmt_ratio(stats["avg_revenue_per_ticket"]),
    ]
    fig = go.Figure(
        go.Table(
            header=dict(values=["Chỉ số", "Giá trị"], fill_color="#102a43", font=dict(color="white", size=13), align=["left", "right"]),
            cells=dict(values=[labels, values], fill_color=["#f8fafc", "white"], font=dict(color=INK, size=13), align=["left", "right"], height=34),
        )
    )
    fig.update_layout(title=dict(text="Tổng quan tập dữ liệu", x=0.02, font=dict(size=18, color=INK)), height=420, margin=dict(l=20, r=20, t=70, b=20))
    charts.append(
        (
            "chart-overview",
            "Tổng quan tập dữ liệu",
            "Tất cả chỉ số được tính trực tiếp từ 78 hàng của checkpoint3.csv.",
            fig,
        )
    )

    counts = [int(item["movies"]) for item in year_stats]
    fig = go.Figure(
        go.Bar(
            x=[str(year) for year in years],
            y=counts,
            text=[fmt_int(value) for value in counts],
            textposition="outside",
            cliponaxis=False,
            marker_color=PRIMARY,
            customdata=[[value] for value in counts],
            hovertemplate="Năm %{x}<br>Số phim: %{customdata[0]}<extra></extra>",
            name="Số phim",
        )
    )
    fig = plotly_layout(fig, "Số lượng phim theo năm phát hành", "Năm phát hành", "Số phim", height=460)
    fig.update_yaxes(range=[0, max(counts) * 1.18])
    charts.append(
        (
            "chart-year-counts",
            "Phân bố phim theo năm phát hành",
            "Giá trị chính xác được hiển thị trên mỗi cột.",
            fig,
        )
    )

    revenue_by_year = [item["revenue"] for item in year_stats]
    fig = go.Figure(
        go.Bar(
            x=[str(year) for year in years],
            y=[float(to_billions(value)) for value in revenue_by_year],
            text=[fmt_ty(value) for value in revenue_by_year],
            textposition="outside",
            cliponaxis=False,
            marker_color=TEAL,
            customdata=[[fmt_vnd(value), fmt_ty(value)] for value in revenue_by_year],
            hovertemplate="Năm %{x}<br>Tổng doanh thu: %{customdata[0]}<br>Đơn vị hiển thị: %{customdata[1]}<extra></extra>",
            name="Doanh thu",
        )
    )
    fig = plotly_layout(fig, "Tổng doanh thu theo năm phát hành", "Năm phát hành", "Doanh thu (tỷ VND)", height=480)
    fig.update_yaxes(range=[0, float(to_billions(max(revenue_by_year))) * 1.18])
    charts.append(
        (
            "chart-revenue-by-year",
            "Tổng doanh thu theo năm",
            "Trục dùng tỷ VND; hover hiển thị VND gốc và tỷ VND.",
            fig,
        )
    )

    top_revenue = list(stats["top_revenue"])
    fig = go.Figure(
        go.Bar(
            y=[wrap_label(str(record["movie_name"])) for record in top_revenue],
            x=[float(to_billions(record["_revenue"])) for record in top_revenue],
            orientation="h",
            text=[fmt_ty(record["_revenue"]) for record in top_revenue],
            textposition="outside",
            cliponaxis=False,
            marker_color=TEAL,
            customdata=[
                [str(record["movie_name"]), int(record["_year"]), fmt_vnd(record["_revenue"])]
                for record in top_revenue
            ],
            hovertemplate="<b>%{customdata[0]}</b><br>Năm: %{customdata[1]}<br>Doanh thu: %{customdata[2]}<extra></extra>",
            name="Doanh thu",
        )
    )
    fig = plotly_layout(fig, "Top 10 phim theo doanh thu", "Doanh thu (tỷ VND)", "Phim", height=580, margin_left=290)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, float(to_billions(top_revenue[0]["_revenue"])) * 1.25])
    charts.append(
        (
            "chart-top-revenue",
            "Top 10 phim theo doanh thu",
            "Xếp hạng giảm dần; tên phim được giữ nguyên trong hover.",
            fig,
        )
    )

    top_tickets = list(stats["top_tickets"])
    fig = go.Figure(
        go.Bar(
            y=[wrap_label(str(record["movie_name"])) for record in top_tickets],
            x=[int(record["_tickets"]) for record in top_tickets],
            orientation="h",
            text=[fmt_int(record["_tickets"]) for record in top_tickets],
            textposition="outside",
            cliponaxis=False,
            marker_color=AMBER,
            customdata=[
                [str(record["movie_name"]), int(record["_year"]), fmt_int(record["_tickets"])]
                for record in top_tickets
            ],
            hovertemplate="<b>%{customdata[0]}</b><br>Năm: %{customdata[1]}<br>Số vé: %{customdata[2]}<br>" + CAVEAT + "<extra></extra>",
            name="Số vé",
        )
    )
    fig = plotly_layout(fig, "Top 10 phim theo tickets_sold", "Số vé (giá trị gốc / ước tính / nhập thủ công)", "Phim", height=580, margin_left=290)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, int(top_tickets[0]["_tickets"]) * 1.25])
    charts.append(
        (
            "chart-top-tickets",
            "Top 10 phim theo số vé",
            CAVEAT,
            fig,
        )
    )

    tickets_by_year = [int(item["tickets"]) for item in year_stats]
    fig = go.Figure(
        go.Bar(
            x=[str(year) for year in years],
            y=tickets_by_year,
            text=[fmt_int(value) for value in tickets_by_year],
            textposition="outside",
            cliponaxis=False,
            marker_color=AMBER,
            customdata=[[fmt_int(value)] for value in tickets_by_year],
            hovertemplate="Năm %{x}<br>Tổng số vé: %{customdata[0]}<br>" + CAVEAT + "<extra></extra>",
            name="Số vé",
        )
    )
    fig = plotly_layout(fig, "Tổng số vé theo năm phát hành", "Năm phát hành", "Tổng số vé", height=480)
    fig.update_yaxes(range=[0, max(tickets_by_year) * 1.18])
    charts.append(
        (
            "chart-tickets-by-year",
            "Tổng số vé theo năm",
            CAVEAT,
            fig,
        )
    )

    genres = list(stats["genres"])
    fig = go.Figure(
        go.Bar(
            y=[wrap_label(name, 30) for name, _ in genres],
            x=[count for _, count in genres],
            orientation="h",
            text=[count for _, count in genres],
            textposition="outside",
            cliponaxis=False,
            marker_color=PRIMARY,
            customdata=[[name, count] for name, count in genres],
            hovertemplate="<b>%{customdata[0]}</b><br>Số phim: %{customdata[1]}<br>Một phim có thể thuộc nhiều thể loại<extra></extra>",
            name="Số phim",
        )
    )
    fig = plotly_layout(fig, "Số phim theo thể loại", "Số phim", "Thể loại", height=max(620, 30 * len(genres)), margin_left=250)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, max(count for _, count in genres) * 1.18])
    charts.append(
        (
            "chart-genres",
            "Phân bố theo thể loại",
            "Trường genre ghép được tách thành từng thể loại trước khi đếm.",
            fig,
        )
    )

    directors = list(stats["directors"])
    director_colors = [AMBER if name == "(Không rõ)" else PRIMARY for name, _ in directors]
    fig = go.Figure(
        go.Bar(
            y=[wrap_label(name, 30) for name, _ in directors],
            x=[count for _, count in directors],
            orientation="h",
            text=[count for _, count in directors],
            textposition="outside",
            cliponaxis=False,
            marker_color=director_colors,
            customdata=[[name, count] for name, count in directors],
            hovertemplate="<b>%{customdata[0]}</b><br>Số phim: %{customdata[1]}<extra></extra>",
            name="Số phim",
        )
    )
    fig = plotly_layout(fig, "Top 10 đạo diễn theo số phim", "Số phim", "Đạo diễn", height=560, margin_left=250)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, max(count for _, count in directors) * 1.18])
    charts.append(
        (
            "chart-directors",
            "Top 10 đạo diễn",
            f"Giá trị đạo diễn thiếu: {stats['missing_directors']}; không gán tên giả.",
            fig,
        )
    )

    scatter_customdata = [
        [
            str(record["movie_name"]),
            int(record["_year"]),
            fmt_vnd(record["_revenue"]),
            fmt_ty(record["_revenue"]),
            fmt_int(record["_tickets"]),
        ]
        for record in records
    ]
    fig = go.Figure(
        go.Scatter(
            x=[float(to_billions(record["_revenue"])) for record in records],
            y=[int(record["_tickets"]) for record in records],
            mode="markers",
            marker=dict(
                size=9,
                color=[int(record["_year"]) for record in records],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Năm", thickness=14, len=0.8),
                line=dict(width=0.5, color="white"),
            ),
            customdata=scatter_customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Năm: %{customdata[1]}"
                "<br>Doanh thu: %{customdata[2]}"
                "<br>Doanh thu (tỷ VND): %{customdata[3]}"
                "<br>Số vé: %{customdata[4]}<br>" + CAVEAT + "<extra></extra>"
            ),
            name="Phim",
        )
    )
    fig = plotly_layout(fig, "Doanh thu so với số vé", "Doanh thu (tỷ VND)", "Số vé", height=600)
    charts.append(
        (
            "chart-revenue-tickets",
            "Doanh thu so với số vé",
            "Mỗi điểm là một phim; hover hiển thị tên phim, năm, doanh thu và số vé.",
            fig,
        )
    )

    ratio = stats["avg_revenue_per_ticket"]
    fig = go.Figure(
        go.Bar(
            y=["Tổng doanh thu / tổng vé"],
            x=[float(ratio)],
            orientation="h",
            text=[fmt_ratio(ratio)],
            textposition="outside",
            cliponaxis=False,
            marker_color=TEAL,
            customdata=[[fmt_vnd(stats["total_revenue"]), fmt_int(stats["total_tickets"])]],
            hovertemplate="%{y}<br>Tổng doanh thu: %{customdata[0]}<br>Tổng vé: %{customdata[1]}<br>Tỷ lệ: %{text}<extra></extra>",
            name="Tỷ lệ",
        )
    )
    fig = plotly_layout(
        fig,
        "Doanh thu trung bình trên mỗi vé ước tính/đã ghi nhận",
        "VND/vé",
        "Chỉ số",
        height=380,
        margin_left=250,
    )
    fig.update_xaxes(range=[0, float(ratio) * 1.35])
    charts.append(
        (
            "chart-avg-revenue-ticket",
            "Doanh thu trung bình trên mỗi vé",
            "Tỷ lệ tổng doanh thu / tổng tickets_sold; không phải giá vé đã xác minh.",
            fig,
        )
    )

    return charts


def decode_js_unicode(value: str) -> str:
    return re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        value,
    )


def build_html(
    charts: list[tuple[str, str, str, go.Figure]],
    stats: dict[str, object],
    source_sha: str,
) -> str:
    metric_cards = [
        ("Tổng phim", fmt_int(stats["rows"]), "78 phim cuối cùng", "blue"),
        ("Phạm vi năm", f"{stats['year_min']}–{stats['year_max']}", "đã loại năm 2019", "teal"),
        ("Tổng doanh thu", fmt_ty(stats["total_revenue"]), fmt_vnd(stats["total_revenue"]), "teal"),
        ("Tổng số vé", fmt_int(stats["total_tickets"]), "gốc / ước tính / nhập thủ công", "amber"),
        ("Doanh thu/phim", fmt_ty(stats["avg_revenue"]), "trung bình 78 phim", "blue"),
        ("Số vé/phim", f"{stats['avg_tickets']:,.0f}".replace(",", "."), "trung bình 78 phim", "amber"),
    ]
    metric_html = []
    for label, value, note, tone in metric_cards:
        metric_html.append(
            f"""
            <article class="metric metric--{tone}">
              <p class="metric__label">{html.escape(label)}</p>
              <p class="metric__value">{html.escape(value)}</p>
              <p class="metric__note">{html.escape(note)}</p>
            </article>
            """
        )

    chart_cards = []
    for index, (div_id, title, subtitle, fig) in enumerate(charts):
        plot_html = to_html(
            fig,
            full_html=False,
            include_plotlyjs=(index == 0),
            config=PLOTLY_CONFIG,
            div_id=div_id,
        )
        chart_cards.append(
            f"""
            <section class="chart-card">
              <header class="chart-card__header">
                <h2>{html.escape(title)}</h2>
                <p>{html.escape(subtitle)}</p>
              </header>
              <div class="chart-card__plot">{plot_html}</div>
            </section>
            """
        )

    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Checkpoint3 | Báo cáo phim điện ảnh 2020–2026</title>
  <link rel="stylesheet" href="assets/css/style.css">
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <p class="hero__eyebrow">Checkpoint3 · Báo cáo tương tác</p>
      <h1>Tổng quan doanh thu và số vé phim điện ảnh 2020–2026</h1>
      <p class="hero__lede">
        Báo cáo được xây dựng từ đúng 78 phim trong
        <code>data/processed/checkpoint3.csv</code>. Mọi biểu đồ hover, phóng to,
        thu nhỏ và bật/tắt chú giải đều hoạt động trực tiếp trong trình duyệt.
      </p>
    </header>

    <aside class="notice" role="note">
      <strong>Ticket caveat:</strong> {html.escape(CAVEAT)}
      <br>
      {html.escape(CAVEAT_VI)} Tỷ lệ doanh thu trên mỗi vé ở cuối báo cáo chỉ là
      phép chia tổng doanh thu cho tổng <code>tickets_sold</code>, không phải giá vé
      được xác minh độc lập.
    </aside>

    <section class="metrics" aria-label="Tổng quan tập dữ liệu">
      {''.join(metric_html)}
    </section>

    <main class="charts">
      {''.join(chart_cards)}
    </main>

    <section class="method">
      <h2>Phương pháp và giới hạn</h2>
      <div class="method__grid">
        <article>
          <h3>Nguồn dữ liệu</h3>
          <p>
            <code>data/processed/checkpoint3.csv</code> — 78 hàng, 6 cột:
            <code>movie_name</code>, <code>release_year</code>, <code>genre</code>,
            <code>director</code>, <code>revenue</code>, <code>tickets_sold</code>.
            Tập dữ liệu gốc không bị chỉnh sửa trong quá trình tạo báo cáo.
          </p>
        </article>
        <article>
          <h3>Doanh thu</h3>
          <p>
            Giá trị <code>revenue</code> được phân tích sang VND bằng Decimal, gồm cả
            định dạng VND có dấu phẩy và định dạng <code>tỷ đồng</code>. Giá trị gốc
            trong CSV được giữ nguyên; biểu đồ hiển thị tỷ VND để dễ đọc.
            Tổng doanh thu: {html.escape(fmt_vnd(stats['total_revenue']))}.
          </p>
        </article>
        <article>
          <h3>Thể loại và đạo diễn</h3>
          <p>
            Trường <code>genre</code> ghép được tách theo dấu phẩy, chấm phẩy, gạch
            đứng hoặc gạch chéo; một phim có thể thuộc nhiều thể loại. Biểu đồ đạo
            diễn lấy 10 nhóm lớn nhất. Giá trị thiếu, nếu có, được gộp là
            “(Không rõ)” mà không gán tên giả.
          </p>
        </article>
        <article>
          <h3>Số vé</h3>
          <p>
            <code>tickets_sold</code> gồm giá trị gốc, giá trị ước tính và giá trị nhập
            thủ công. {html.escape(CAVEAT)} Không có cờ trong CSV để phân biệt từng
            dòng, nên báo cáo không suy luận giá trị thực tế cho từng phim.
          </p>
        </article>
      </div>
    </section>

    <footer class="footer">
      <p>
        Plotly.js được nhúng trực tiếp; CSS dùng tệp local. Nguồn CSV SHA-256:
        <code>{html.escape(source_sha)}</code>
      </p>
    </footer>
  </div>
</body>
</html>
"""


def validate_outputs(
    records: list[dict[str, object]],
    stats: dict[str, object],
    source_sha_before: str,
    source_sha_after: str,
    old_manifest_before: dict[str, str],
    static_written: list[str],
) -> None:
    if source_sha_before != source_sha_after:
        raise RuntimeError("Source CSV SHA-256 changed during report generation")
    if file_manifest(
        [ROOT / "reports" / "plotly_visualization", ROOT / "reports" / "visualizations"]
    ) != old_manifest_before:
        raise RuntimeError("Old visualization directory changed")

    if not HTML_PATH.exists() or HTML_PATH.stat().st_size == 0:
        raise RuntimeError("index.html missing or empty")
    if not CSS_PATH.exists() or CSS_PATH.stat().st_size == 0:
        raise RuntimeError("style.css missing or empty")

    html_text = HTML_PATH.read_text(encoding="utf-8")
    decoded_html = decode_js_unicode(html_text)
    if html_text.count("Plotly.newPlot") < len(CHART_IDS):
        raise RuntimeError("Not all Plotly charts were rendered")
    for chart_id in CHART_IDS:
        if f'id="{chart_id}"' not in html_text:
            raise RuntimeError(f"Missing chart div: {chart_id}")
    if "plotly.js" not in html_text.lower():
        raise RuntimeError("Inline Plotly JS not found")
    if '<link rel="stylesheet" href="assets/css/style.css">' not in html_text:
        raise RuntimeError("Local CSS reference missing")
    if re.search(r"<script[^>]+src=[\"']https?://", html_text, re.IGNORECASE):
        raise RuntimeError("External script dependency found")
    if CAVEAT not in html_text:
        raise RuntimeError("Ticket caveat missing from HTML")
    if "92" in html_text and "92 hàng" in html_text:
        raise RuntimeError("Old 92-row dataset reference found")

    for record in records:
        if str(record["movie_name"]) not in decoded_html:
            raise RuntimeError(f"Movie name missing from decoded HTML: {record['movie_name']}")

    if static_written != STATIC_FILES:
        raise RuntimeError("Static chart set does not match expected files")
    for filename in STATIC_FILES:
        path = STATIC_DIR / filename
        if not path.exists() or path.stat().st_size < 10_000:
            raise RuntimeError(f"Static chart missing or too small: {filename}")
        if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(f"Static chart is not a PNG: {filename}")

    if stats["rows"] != 78:
        raise RuntimeError("Report did not use exactly 78 rows")


def main() -> None:
    records, source_sha_before = load_data()
    stats = aggregate(records)

    old_manifest_before = file_manifest(
        [ROOT / "reports" / "plotly_visualization", ROOT / "reports" / "visualizations"]
    )

    CSS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLOTLY_DIR.mkdir(parents=True, exist_ok=True)
    CSS_PATH.write_text(CSS, encoding="utf-8")

    static_written = build_static_charts(records, stats)
    charts = build_plotly_charts(records, stats)
    HTML_PATH.write_text(build_html(charts, stats, source_sha_before), encoding="utf-8")

    source_sha_after = sha256_bytes(CSV_PATH.read_bytes())
    validate_outputs(
        records,
        stats,
        source_sha_before,
        source_sha_after,
        old_manifest_before,
        static_written,
    )

    print(f"source={CSV_PATH.as_posix()}")
    print(f"source_sha256={source_sha_before}")
    print(f"rows={stats['rows']} columns={len(EXPECTED_COLUMNS)}")
    print(f"static_charts={len(static_written)}")
    print(f"plotly_charts={len(charts)}")
    print(f"total_revenue_vnd={stats['total_revenue']}")
    print(f"total_tickets={stats['total_tickets']}")
    print(f"avg_revenue={stats['avg_revenue']}")
    print(f"avg_tickets={stats['avg_tickets']}")
    print(f"avg_revenue_per_ticket={stats['avg_revenue_per_ticket']}")
    print("VALIDATION_PASSED")


if __name__ == "__main__":
    main()
