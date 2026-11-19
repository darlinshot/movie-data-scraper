from __future__ import annotations

import html
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.io import to_html

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "analytics" / "movie_analytics_2020_2026.csv"
OUTPUT_DIR = Path(__file__).resolve().parent
HTML_PATH = OUTPUT_DIR / "index.html"

EXPECTED_COLUMNS = [
    "movie_name",
    "release_year",
    "genre",
    "director",
    "revenue",
    "tickets_sold",
]

PRIMARY = "#2563eb"
TEAL = "#0f766e"
AMBER = "#b45309"
SLATE = "#243b53"
GRID = "#e2e8f0"
PANEL = "#f8fafc"

CONFIG = {
    "responsive": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}


def parse_revenue(value: str) -> Decimal:
    value = value.strip()
    exact = re.fullmatch(r"\d{1,3}(?:,\d{3})+₫", value)
    if exact:
        return Decimal(value[:-1].replace(",", ""))
    billions = re.fullmatch(r"(\d+) tỷ", value)
    if billions:
        return Decimal(billions.group(1)) * Decimal(1_000_000_000)
    raise ValueError(f"Cannot parse revenue value safely: {value!r}")


def fmt_int(value: int | Decimal | float) -> str:
    return f"{int(value):,}".replace(",", ".")


def to_billions(value: Decimal) -> Decimal:
    return value / Decimal(1_000_000_000)


def fmt_vnd(value: Decimal) -> str:
    return f"{fmt_int(value)}₫"


def fmt_ty(value: Decimal) -> str:
    formatted = f"{to_billions(value):,.2f}"
    formatted = formatted.replace(",", "_NGHIN_").replace(".", ",").replace("_NGHIN_", ".")
    return formatted + " tỷ"


def split_genres(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;|/]+", str(value)) if part.strip()]


def base_layout(
    fig: go.Figure,
    title: str,
    x_title: str,
    y_title: str,
    height: int = 520,
    margin_left: int = 80,
) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.02, xanchor="left", font=dict(size=18, color="#102a43")),
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


def load_data() -> tuple[pd.DataFrame, dict[str, object]]:
    df = pd.read_csv(
        CSV_PATH,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
        na_filter=False,
    )

    if len(df) != 69:
        raise SystemExit(f"Expected 69 rows, found {len(df)}")
    if list(df.columns) != EXPECTED_COLUMNS:
        raise SystemExit(f"Unexpected columns: {list(df.columns)}")

    years = pd.to_numeric(df["release_year"], errors="coerce")
    if years.isna().any() or not years.between(2020, 2026).all():
        raise SystemExit("release_year contains invalid or out-of-range values")
    if df["tickets_sold"].str.strip().eq("").any():
        raise SystemExit("tickets_sold contains missing values")

    df = df.copy()
    df["_year"] = years.astype(int)
    df["_tickets"] = df["tickets_sold"].astype(int)
    df["_revenue_vnd"] = df["revenue"].map(parse_revenue)
    df["_revenue_float"] = df["_revenue_vnd"].map(float)

    director_raw = df["director"].str.strip()
    df["_director"] = director_raw.replace("", "(Không rõ)")
    missing_directors = int(director_raw.eq("").sum())

    total_revenue = sum(df["_revenue_vnd"], Decimal(0))
    total_tickets = int(df["_tickets"].sum())
    stats = {
        "rows": len(df),
        "year_min": int(df["_year"].min()),
        "year_max": int(df["_year"].max()),
        "total_revenue": total_revenue,
        "total_tickets": total_tickets,
        "missing_directors": missing_directors,
        "revenue_parsed": int(df["_revenue_vnd"].notna().sum()),
    }
    return df, stats


def build_charts(df: pd.DataFrame) -> list[tuple[str, str, str, go.Figure]]:
    charts: list[tuple[str, str, str, go.Figure]] = []

    year_stats = (
        df.groupby("_year")
        .agg(movies=("movie_name", "count"), revenue=("_revenue_vnd", "sum"), tickets=("_tickets", "sum"))
        .reset_index()
        .sort_values("_year")
    )

    fig = go.Figure(
        go.Bar(
            x=year_stats["_year"],
            y=year_stats["movies"],
            text=year_stats["movies"],
            textposition="outside",
            cliponaxis=False,
            marker_color=PRIMARY,
            hovertemplate="Năm %{x}<br>Số phim: %{y}<extra></extra>",
            name="Số phim",
        )
    )
    fig = base_layout(
        fig,
        "Số lượng phim theo năm phát hành",
        "Năm phát hành",
        "Số phim",
        height=460,
    )
    fig.update_yaxes(range=[0, int(year_stats["movies"].max()) * 1.18])
    charts.append(
        (
            "chart-year-counts",
            "Phân bố phim theo năm phát hành",
            "Giá trị trên mỗi cột là số phim chính xác trong từng năm.",
            fig,
        )
    )

    fig = go.Figure(
        go.Bar(
            x=year_stats["_year"],
            y=[float(to_billions(v)) for v in year_stats["revenue"]],
            text=[fmt_ty(v) for v in year_stats["revenue"]],
            textposition="outside",
            cliponaxis=False,
            marker_color=TEAL,
            customdata=[[fmt_vnd(v), fmt_ty(v)] for v in year_stats["revenue"]],
            hovertemplate=(
                "Năm %{x}<br>Tổng doanh thu: %{customdata[0]}"
                "<br>Đơn vị hiển thị: %{customdata[1]}<extra></extra>"
            ),
            name="Doanh thu",
        )
    )
    fig = base_layout(
        fig,
        "Tổng doanh thu theo năm phát hành",
        "Năm phát hành",
        "Tổng doanh thu (tỷ VND)",
        height=480,
    )
    fig.update_yaxes(range=[0, float(to_billions(year_stats["revenue"].max())) * 1.18])
    charts.append(
        (
            "chart-revenue-by-year",
            "Tổng doanh thu theo năm",
            "Trục dùng tỷ VND; hover hiển thị số tiền VND gốc và tỷ VND.",
            fig,
        )
    )

    top_revenue = df.nlargest(10, "_revenue_float").sort_values("_revenue_float")
    fig = go.Figure(
        go.Bar(
            y=top_revenue["movie_name"],
            x=[float(to_billions(v)) for v in top_revenue["_revenue_vnd"]],
            orientation="h",
            text=[fmt_ty(v) for v in top_revenue["_revenue_vnd"]],
            textposition="outside",
            cliponaxis=False,
            marker_color=TEAL,
            customdata=[
                [int(y), fmt_vnd(v), fmt_ty(v)]
                for y, v in zip(top_revenue["_year"], top_revenue["_revenue_vnd"])
            ],
            hovertemplate=(
                "<b>%{y}</b><br>Năm: %{customdata[0]}"
                "<br>Doanh thu: %{customdata[1]}"
                "<br>Đơn vị hiển thị: %{customdata[2]}<extra></extra>"
            ),
            name="Doanh thu",
        )
    )
    fig = base_layout(
        fig,
        "Top 10 phim theo doanh thu",
        "Doanh thu (tỷ VND)",
        "Phim",
        height=560,
        margin_left=270,
    )
    fig.update_xaxes(range=[0, float(to_billions(Decimal(top_revenue["_revenue_vnd"].max()))) * 1.25])
    charts.append(
        (
            "chart-top-revenue",
            "Top 10 phim theo doanh thu",
            "Doanh thu được lấy từ cột revenue gốc, chỉ chuyển đơn vị để hiển thị.",
            fig,
        )
    )

    top_tickets = df.nlargest(10, "_tickets").sort_values("_tickets")
    fig = go.Figure(
        go.Bar(
            y=top_tickets["movie_name"],
            x=top_tickets["_tickets"],
            orientation="h",
            text=[fmt_int(v) for v in top_tickets["_tickets"]],
            textposition="outside",
            cliponaxis=False,
            marker_color=AMBER,
            customdata=[[int(y)] for y in top_tickets["_year"]],
            hovertemplate=(
                "<b>%{y}</b><br>Năm: %{customdata[0]}"
                "<br>Số vé: %{x:,.0f}"
                "<br>Lưu ý: cột này gồm 5 giá trị gốc và 64 giá trị ước tính"
                "<extra></extra>"
            ),
            name="Số vé",
        )
    )
    fig = base_layout(
        fig,
        "Top 10 phim theo tickets_sold (5 gốc + 64 ước tính)",
        "Số vé (hỗn hợp gốc và ước tính)",
        "Phim",
        height=560,
        margin_left=270,
    )
    fig.update_xaxes(range=[0, int(top_tickets["_tickets"].max()) * 1.25])
    charts.append(
        (
            "chart-top-tickets",
            "Top 10 phim theo số vé",
            "Không trình bày các giá trị này là doanh số vé đã xác minh.",
            fig,
        )
    )

    fig = go.Figure(
        go.Bar(
            x=year_stats["_year"],
            y=year_stats["tickets"],
            text=[fmt_int(v) for v in year_stats["tickets"]],
            textposition="outside",
            cliponaxis=False,
            marker_color=AMBER,
            customdata=[[int(v)] for v in year_stats["tickets"]],
            hovertemplate=(
                "Năm %{x}<br>Tổng số vé: %{customdata[0]:,}"
                "<br>Lưu ý: 5 giá trị gốc + 64 giá trị ước tính<extra></extra>"
            ),
            name="Số vé",
        )
    )
    fig = base_layout(
        fig,
        "Tổng số vé theo năm phát hành (5 gốc + 64 ước tính)",
        "Năm phát hành",
        "Tổng số vé (hỗn hợp gốc và ước tính)",
        height=480,
    )
    fig.update_yaxes(range=[0, int(year_stats["tickets"].max()) * 1.18])
    charts.append(
        (
            "chart-tickets-by-year",
            "Tổng số vé theo năm",
            "Một phim có thể đóng góp nhiều thể loại; số vé thì không bị nhân đôi.",
            fig,
        )
    )

    genre_counter: Counter[str] = Counter()
    for value in df["genre"]:
        genre_counter.update(split_genres(value))
    genre_items = sorted(genre_counter.items(), key=lambda item: (item[1], item[0]))
    fig = go.Figure(
        go.Bar(
            y=[name for name, _ in genre_items],
            x=[count for _, count in genre_items],
            orientation="h",
            text=[count for _, count in genre_items],
            textposition="outside",
            cliponaxis=False,
            marker_color=PRIMARY,
            customdata=[[count] for _, count in genre_items],
            hovertemplate=(
                "<b>%{y}</b><br>Số phim: %{customdata[0]}"
                "<br>Một phim có thể thuộc nhiều thể loại<extra></extra>"
            ),
            name="Số phim",
        )
    )
    fig = base_layout(
        fig,
        "Số phim theo thể loại (tách giá trị ghép)",
        "Số phim",
        "Thể loại",
        height=min(max(560, 26 * len(genre_items)), 1600),
        margin_left=230,
    )
    fig.update_xaxes(range=[0, max(count for _, count in genre_items) * 1.2])
    charts.append(
        (
            "chart-genres",
            "Phân bố theo thể loại",
            "Chuỗi thể loại ghép được tách theo dấu phẩy, chấm phẩy, gạch đứng hoặc gạch chéo.",
            fig,
        )
    )

    director_counts = df["_director"].value_counts().sort_values()
    director_colors = [
        AMBER if director == "(Không rõ)" else PRIMARY for director in director_counts.index
    ]
    fig = go.Figure(
        go.Bar(
            y=director_counts.index,
            x=director_counts.values,
            orientation="h",
            text=director_counts.values,
            textposition="outside",
            cliponaxis=False,
            marker_color=director_colors,
            customdata=[[int(v)] for v in director_counts.values],
            hovertemplate="<b>%{y}</b><br>Số phim: %{customdata[0]}<extra></extra>",
            name="Số phim",
        )
    )
    fig = base_layout(
        fig,
        "Số phim theo đạo diễn",
        "Số phim",
        "Đạo diễn",
        height=min(max(560, 24 * len(director_counts)), 1600),
        margin_left=240,
    )
    fig.update_xaxes(range=[0, int(director_counts.max()) * 1.25])
    charts.append(
        (
            "chart-directors",
            "Phân bố theo đạo diễn",
            "Giá trị thiếu, nếu có, được gộp rõ ràng là “(Không rõ)” mà không gán tên giả.",
            fig,
        )
    )

    hover_data = [
        [
            int(year),
            fmt_vnd(Decimal(revenue)),
            fmt_ty(Decimal(revenue)),
            fmt_int(int(tickets)),
        ]
        for year, revenue, tickets in zip(df["_year"], df["_revenue_vnd"], df["_tickets"])
    ]
    fig = go.Figure(
        go.Scatter(
            x=[float(to_billions(v)) for v in df["_revenue_vnd"]],
            y=df["_tickets"],
            mode="markers",
            text=df["movie_name"],
            customdata=hover_data,
            marker=dict(
                size=10,
                color=df["_year"],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Năm", thickness=14, len=0.8),
                line=dict(width=0.5, color="white"),
            ),
            hovertemplate=(
                "<b>%{text}</b><br>Năm: %{customdata[0]}"
                "<br>Doanh thu: %{customdata[1]}"
                "<br>Doanh thu (tỷ VND): %{customdata[2]}"
                "<br>Số vé: %{customdata[3]}"
                "<br>tickets_sold: 5 giá trị gốc + 64 ước tính; không xác định từng dòng"
                "<extra></extra>"
            ),
            name="Phim",
        )
    )
    fig = base_layout(
        fig,
        "Doanh thu so với số vé",
        "Doanh thu (tỷ VND)",
        "Số vé (5 gốc + 64 ước tính)",
        height=600,
    )
    charts.append(
        (
            "chart-revenue-tickets",
            "Doanh thu so với số vé",
            "Mỗi điểm là một phim. Màu biểu thị năm phát hành; không có đường xu hướng vì dữ liệu vé là hỗn hợp.",
            fig,
        )
    )

    return charts


def build_html(df: pd.DataFrame, stats: dict[str, object], charts: list[tuple[str, str, str, go.Figure]]) -> str:
    total_revenue = stats["total_revenue"]
    assert isinstance(total_revenue, Decimal)
    missing_directors = int(stats["missing_directors"])

    metrics = [
        {
            "label": "Tổng phim",
            "value": fmt_int(stats["rows"]),
            "note": "phim trong tập dữ liệu cuối",
            "tone": "blue",
        },
        {
            "label": "Phạm vi năm",
            "value": f"{stats['year_min']}–{stats['year_max']}",
            "note": "năm phát hành hợp lệ",
            "tone": "teal",
        },
        {
            "label": "Tổng doanh thu",
            "value": fmt_ty(total_revenue),
            "note": f"chính xác: {fmt_vnd(total_revenue)}",
            "tone": "teal",
        },
        {
            "label": "Tổng số vé",
            "value": fmt_int(stats["total_tickets"]),
            "note": "5 giá trị gốc + 64 giá trị ước tính",
            "tone": "amber",
        },
    ]

    metric_html = []
    for metric in metrics:
        metric_html.append(
            f"""
            <article class="metric metric--{html.escape(metric['tone'])}">
              <p class="metric__label">{html.escape(str(metric['label']))}</p>
              <p class="metric__value">{html.escape(str(metric['value']))}</p>
              <p class="metric__note">{html.escape(str(metric['note']))}</p>
            </article>
            """
        )

    chart_cards = []
    for index, (div_id, title, subtitle, fig) in enumerate(charts):
        plot_html = to_html(
            fig,
            full_html=False,
            include_plotlyjs=(index == 0),
            config=CONFIG,
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

    director_check = (
        f"Tệp hiện tại có {missing_directors} giá trị đạo diễn thiếu."
        if missing_directors
        else "Tệp hiện tại có 0 giá trị đạo diễn thiếu; bản mô tả yêu cầu kỳ vọng 3, nhưng báo cáo này phản ánh dữ liệu thực tế."
    )

    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Phim Việt 2020–2026 | Báo cáo tương tác</title>
  <link rel="stylesheet" href="assets/css/style.css">
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <p class="hero__eyebrow">Báo cáo dữ liệu điện ảnh · 2020–2026</p>
      <h1>Tổng quan doanh thu và số vé phim điện ảnh</h1>
      <p class="hero__lede">
        Báo cáo tương tác được xây dựng từ 69 bộ phim trong tập dữ liệu phân tích cuối cùng.
        Tất cả biểu đồ cho phép hover, phóng to, thu nhỏ và bật/tắt chú giải.
      </p>
    </header>

    <aside class="notice" role="note">
      <strong>Lưu ý quan trọng về <code>tickets_sold</code>:</strong>
      cột này gồm <strong>5 giá trị gốc</strong> và <strong>64 giá trị ước tính</strong>.
      Các giá trị ước tính được tính từ công thức giá vé trung bình gộp, hiệu chỉnh từ 3 phim được chọn;
      2 hàng hiệu chỉnh không nhất quán đã bị loại khỏi công thức nhưng giá trị gốc của chúng vẫn được giữ lại.
      Vì tệp CSV cuối không có cờ đánh dấu, <strong>không thể phân biệt từng dòng là gốc hay ước tính</strong>.
      Do đó, số vé ở đây <strong>không phải là doanh số vé đã xác minh</strong>.
    </aside>

    <section class="metrics" aria-label="Tổng quan tập dữ liệu">
      {''.join(metric_html)}
    </section>

    <main class="charts">
      {''.join(chart_cards)}
    </main>

    <section class="method">
      <h2>Phương pháp và giới hạn dữ liệu</h2>
      <div class="method__grid">
        <article>
          <h3>Nguồn dữ liệu</h3>
          <p>
            <code>data/analytics/movie_analytics_2020_2026.csv</code> — 69 hàng, 6 cột:
            <code>movie_name</code>, <code>release_year</code>, <code>genre</code>,
            <code>director</code>, <code>revenue</code>, <code>tickets_sold</code>.
          </p>
        </article>
        <article>
          <h3>Doanh thu</h3>
          <p>
            Giá trị revenue được phân tích sang VND để tính toán và hiển thị thống nhất theo tỷ VND.
            {stats['revenue_parsed']}/69 giá trị phân tích thành công; chuỗi gốc trong CSV không bị thay đổi.
          </p>
        </article>
        <article>
          <h3>Thể loại và đạo diễn</h3>
          <p>
            Thể loại ghép được tách thành từng thể loại trước khi đếm; một phim có thể thuộc nhiều nhóm.
            Giá trị đạo diễn thiếu, nếu có, được gộp là “(Không rõ)”. {director_check}
          </p>
        </article>
        <article>
          <h3>Số vé</h3>
          <p>
            Cột <code>tickets_sold</code> là hỗn hợp giữ liệu gốc và ước tính. Các biểu đồ liên quan
            luôn ghi rõ điều này và không suy luận doanh số thực tế cho từng phim.
          </p>
        </article>
      </div>
    </section>

    <footer class="footer">
      <p>Plotly được nhúng trực tiếp vào tệp HTML; không yêu cầu dịch vụ bên ngoài hoặc máy chủ.</p>
    </footer>
  </div>
</body>
</html>
"""


def main() -> None:
    df, stats = load_data()
    charts = build_charts(df)
    html_content = build_html(df, stats, charts)
    HTML_PATH.write_text(html_content, encoding="utf-8")
    print(f"generated={HTML_PATH}")
    print(f"rows={stats['rows']} charts={len(charts)}")
    print(f"sha256_csv={__import__('hashlib').sha256(CSV_PATH.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
