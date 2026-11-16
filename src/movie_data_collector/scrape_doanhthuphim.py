from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page

from .config import DOANHTHUPHIM_URL, DTP_PROGRESS
from .utils import clean_text, polite_delay, read_jsonl, with_retry


async def _discover_movie_links(page: Page) -> list[dict[str, Any]]:
    return await page.evaluate(
        r"""
        () => {
          const abs = (href) => { try { return new URL(href, location.href).href; } catch { return href; } };
          const norm = s => (s||'').replace(/\s+/g,' ').trim();
          const results = [];
          const seen = new Set();
          // Prefer anchors that look like movie cards (have rank/revenue in nearby text) but keep all /phim/ links as fallback
          const anchors = Array.from(document.querySelectorAll('a[href*="/phim/"]'));
          for (const a of anchors) {
            const href = abs(a.getAttribute('href'));
            if (!href || !/\/phim\/[^\/?#]+/i.test(href)) continue;
            if (seen.has(href)) continue;
            // try to find a compact container for this specific movie
            let container = a;
            for (const sel of ['article', 'li', '[class*="card"]', '[class*="movie"]', '[class*="item"]', 'div']) {
              const c = a.closest(sel);
              if (!c) continue;
              const t = norm(c.innerText);
              const links = c.querySelectorAll('a[href*="/phim/"]').length;
              if (t && links <= 2 && t.length <= 400) { container = c; break; }
            }
            let text = norm(container.innerText || a.innerText);
            if (!text || text.length > 500) text = norm(a.innerText);
            const title = norm(a.innerText) || text;
            seen.add(href);
            results.push({href, title, text});
          }
          return results;
        }
        """
    )


async def _click_show_more_until_done(page: Page, max_clicks: int = 1000) -> None:
    last_count = -1
    stagnant = 0
    for _ in range(max_clicks):
        links = await _discover_movie_links(page)
        count = len(links)
        if count == last_count:
            stagnant += 1
        else:
            stagnant = 0
        last_count = count
        if stagnant >= 4:
            return
        clicked = await page.evaluate(
            r"""
            () => {
              const norm = s => (s || '').replace(/\s+/g,' ').trim().toLowerCase();
              const candidates = Array.from(document.querySelectorAll('button,a,div[role="button"],span'));
              for (const el of candidates) {
                const t = norm(el.innerText || el.textContent);
                if (!t) continue;
                if (t === 'xem chi tiết' || t === 'bảng đầy đủ') continue;
                if (t.includes('xem thêm') || t.includes('xem them') || t.includes('load more') || t.includes('tải thêm')) {
                  const style = window.getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  if (style.display === 'none' || style.visibility === 'hidden' || rect.width === 0) continue;
                  el.click();
                  return t;
                }
              }
              for (const a of Array.from(document.querySelectorAll('a[href]'))) {
                const t = norm(a.innerText || a.textContent);
                if (t.includes('xem toàn bộ')) { a.click(); return t; }
              }
              return null;
            }
            """
        )
        if not clicked:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1200)
            links2 = await _discover_movie_links(page)
            if len(links2) <= count and stagnant >= 1:
                return
            continue
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await page.wait_for_timeout(1400)
        await polite_delay(0.2, 0.6)


def _clean_title_guess(text: str | None) -> str | None:
    if not text:
        return None
    t = re.sub(r"\s+", " ", text).strip()
    # remove leading rank markers and years sometimes embedded
    t = re.sub(r"^(#?\d+\s+)+", "", t)
    # cut at common trailing markers
    for marker in ["Chi tiết", "Xem chi tiết", "ĐD:", "Đạo diễn:", "tỷ đồng", "tỷ", "→"]:
        idx = t.find(marker)
        if idx > 0:
            # keep left side if it looks like title
            left = t[:idx].strip(" -·|")
            if left:
                t = left
                break
    # drop leading year token if followed by title
    t = re.sub(r"^(19\d{2}|20\d{2})\s+", "", t).strip()
    return t or None


async def collect_movie_list(page: Page) -> list[dict[str, Any]]:
    await with_retry(
        lambda: page.goto(DOANHTHUPHIM_URL, wait_until="domcontentloaded", timeout=60000),
        label="goto doanhthuphim",
    )
    await page.wait_for_timeout(1800)
    await _click_show_more_until_done(page)
    raw = await _discover_movie_links(page)

    by_url: dict[str, dict[str, Any]] = {}
    for item in raw:
        url = item.get("href")
        if not url:
            continue
        # ignore non-movie utility links
        if any(x in url for x in ["#bang-xep-hang", "/tong-hop", "/toan-cau", "/phuong-phap"]):
            if "/phim/" not in url:
                continue
        title_guess = _clean_title_guess(item.get("title") or item.get("text"))
        rec = {
            "movie_name_guess": title_guess,
            "source_url_doanhthuphim": url,
            "raw_link_text": clean_text(item.get("text") or item.get("title")),
        }
        if url not in by_url:
            by_url[url] = rec
        else:
            # prefer cleaner/shorter title guess
            prev = by_url[url].get("movie_name_guess") or ""
            cur = rec.get("movie_name_guess") or ""
            if cur and (not prev or len(cur) < len(prev)):
                by_url[url] = rec
    return list(by_url.values())


async def fetch_movie_detail(page: Page, url: str | None) -> dict[str, Any]:
    if not url:
        return {}
    async def _go():
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await with_retry(_go, label=f"dtp detail {url}")
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(1200)
    data = await page.evaluate(
        r"""
        () => {
          const norm = s => (s||'').toString().replace(/\s+/g,' ').trim();
          const h1 = norm(document.querySelector('h1')?.innerText) || null;
          const bodyText = document.body.innerText || '';
          const body = norm(bodyText);
          return {h1, body, bodyText};
        }
        """
    )
    h1 = clean_text(data.get("h1"))
    body = data.get("body") or ""
    body_text = data.get("bodyText") or ""

    # Movie title usually "Doanh thu phim X"
    movie_name = None
    if h1:
        m = re.match(r"Doanh thu phim\s+(.+)$", h1, flags=re.I)
        movie_name = m.group(1).strip() if m else h1

    # Intro line often: "2025 Đạo diễn: ... · Khởi chiếu: 15/08/2025 · Lịch sử, Chiến tranh, Chính kịch"
    director = None
    release = None
    genre = None
    # search in raw lines for the line containing director/release
    for line in [l.strip() for l in body_text.splitlines() if l.strip()]:
        if "Đạo diễn" in line or "Khởi chiếu" in line:
            dm = re.search(r"Đạo diễn:\s*([^·\n]+)", line)
            if dm:
                director = dm.group(1).strip()
            rm = re.search(r"Khởi chiếu:\s*([^·\n]+)", line)
            if rm:
                release = rm.group(1).strip()
            # genre often last segment(s) after release
            parts = [p.strip() for p in line.split("·") if p.strip()]
            # parts like ['2025 Đạo diễn: Đặng Thái Huyền', 'Khởi chiếu: 15/08/2025', 'Lịch sử, Chiến tranh, Chính kịch']
            genre_parts = [p for p in parts if not re.search(r"Đạo diễn|Khởi chiếu|\b(19\d{2}|20\d{2})\b", p)]
            if genre_parts:
                genre = ", ".join(genre_parts)
            break

    year = None
    src_year = release or body
    ym = re.search(r"\b(19\d{2}|20\d{2})\b", src_year)
    if ym:
        year = ym.group(1)

    # Cumulative revenue: prefer explicit main totals; avoid "Doanh thu các phim khác" section
    main_body = body
    cut_markers = [
        "Doanh thu các phim khác",
        "Phim đang chiếu",
        "Bảng xếp hạng mọi thời đại",
        "Phòng vé toàn cầu",
    ]
    cut_idx = len(main_body)
    for marker in cut_markers:
        idx = main_body.find(marker)
        if idx != -1:
            cut_idx = min(cut_idx, idx)
    main_body = main_body[:cut_idx]

    revenue = None
    for pat in [
        r"DOANH THU GHI NHẬN[^\d]{0,120}?(hơn\s*)?[\d\.,]+\s*(?:tỷ|triệu)",
        r"Ghi nhận cao nhất:\s*(hơn\s*)?[\d\.,]+\s*(?:tỷ|triệu)",
        r"Tổng kết phòng vé\s*(hơn\s*)?[\d\.,]+\s*(?:tỷ|triệu)",
    ]:
        m = re.search(pat, main_body, flags=re.I)
        if m:
            rv = re.search(r"(hơn\s*)?[\d\.,]+\s*(?:tỷ|triệu)", m.group(0), flags=re.I)
            if rv:
                revenue = rv.group(0).strip()
                break
    if not revenue:
        # fallback: first prominent revenue-like figure in main section
        m = re.search(r"(hơn\s*)?[\d\.,]+\s*(?:tỷ|triệu)\b", main_body, flags=re.I)
        if m:
            revenue = m.group(0).strip()

    # try to split english/original title from movie_name if present in parentheses
    original_title = None
    if movie_name:
        pm = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", movie_name)
        if pm:
            inside = pm.group(2).strip()
            if inside and not re.fullmatch(r"\d{4}", inside):
                original_title = inside

    return {
        "detail_title": movie_name or h1,
        "original_title": clean_text(original_title),
        "release_year": clean_text(year or release),
        "genre": clean_text(genre),
        "director": clean_text(director),
        "revenue_doanhthuphim_detail": clean_text(revenue),
        "raw_body_snippet": body[:2000],
    }


def load_progress_urls(path=DTP_PROGRESS) -> set[str]:
    rows = read_jsonl(path)
    urls = set()
    for r in rows:
        u = r.get("source_url_doanhthuphim")
        if u:
            urls.add(u)
    return urls
