from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from playwright.async_api import Page

from .config import BOXOFFICEVIETNAM_URL
from .utils import clean_text, polite_delay, with_retry


def _is_placeholder_metric(value: str | None) -> bool:
    if not value:
        return True
    v = value.strip().lower()
    if v in {"-", "n/a", "na", "đang cập nhật", "updating"}:
        return True
    # observed premium placeholders
    if v.replace(",", "").replace(".", "") in {"888888", "0", "000"}:
        return True
    return False


async def search_movie(page: Page, query: str) -> list[dict[str, Any]]:
    if not query:
        return []

    async def _open():
        await page.goto(BOXOFFICEVIETNAM_URL, wait_until="domcontentloaded", timeout=60000)

    await with_retry(_open, label="goto boxofficevietnam")
    await page.wait_for_timeout(1200)

    # Use the specific search input observed on site
    filled = False
    try:
        loc = page.locator('input[name="s"][placeholder="Enter Movies or Series Title"]').first
        if await loc.count() > 0:
            await loc.fill(query)
            await loc.press("Enter")
            filled = True
    except Exception:
        filled = False

    if not filled:
        for url in [
            f"{BOXOFFICEVIETNAM_URL.rstrip('/')}/?post_type=movie&s={quote_plus(query)}",
            f"{BOXOFFICEVIETNAM_URL.rstrip('/')}/?s={quote_plus(query)}",
        ]:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1200)
                break
            except Exception:
                continue

    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(1500)

    results = await page.evaluate(
        r"""
        (q) => {
          const abs = (href) => { try { return new URL(href, location.href).href; } catch { return href; } };
          const qn = (q||'').toLowerCase();
          const out = [];
          const seen = new Set();
          for (const a of Array.from(document.querySelectorAll('a[href]'))) {
            const href = abs(a.getAttribute('href'));
            if (!href || seen.has(href)) continue;
            if (!/\/movie\//i.test(href)) continue;
            const title = (a.innerText || '').replace(/\s+/g,' ').trim();
            if (!title || title.length < 2) continue;
            // skip generic nav
            if (/^trang chủ|^blog|^fanpage|^liên hệ|^tài khoản|^đăng/i.test(title)) continue;
            seen.add(href);
            const card = a.closest('article, .movie, .item, li, .card, div') || a;
            out.push({title, href, context: (card.innerText || '').replace(/\s+/g,' ').trim().slice(0,500)});
          }
          return out.slice(0, 30);
        }
        """,
        query,
    )

    by_href: dict[str, dict[str, Any]] = {}
    for r in results:
        href = r.get("href")
        if not href:
            continue
        prev = by_href.get(href)
        if not prev or len((r.get("title") or "")) > len((prev.get("title") or "")):
            by_href[href] = r
    return list(by_href.values())


async def fetch_movie_detail(page: Page, url: str) -> dict[str, Any]:
    async def _go():
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await with_retry(_go, label=f"bov detail {url}")
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(1200)
    data = await page.evaluate(
        r"""
        () => {
          const norm = s => (s||'').toString().replace(/\s+/g,' ').trim();
          const body = norm(document.body.innerText || '');
          const title = norm(document.querySelector('h1')?.innerText) || norm(document.title);
          const getAfterLabel = (label) => {
            const re = new RegExp(label + '\\s*([\\d\\.,]+(?:₫|đ| VNĐ|%)?)', 'i');
            const m = body.match(re);
            return m ? norm(m[1]) : null;
          };
          // try structured blocks by scanning lines
          const lines = (document.body.innerText || '').split('\n').map(norm).filter(Boolean);
          const findLineValue = (label) => {
            const idx = lines.findIndex(l => l.toLowerCase() === label.toLowerCase() || l.toLowerCase().startsWith(label.toLowerCase()+':') || l.toLowerCase().includes(label.toLowerCase()));
            if (idx === -1) return null;
            const line = lines[idx];
            const m = line.match(/:\s*(.+)$/);
            if (m) return norm(m[1]);
            if (idx + 1 < lines.length) return norm(lines[idx+1]);
            return null;
          };
          return {title, body, lines: lines.slice(0,120), getAfterLabel: {
            doanhso: getAfterLabel('Doanh số'),
            suatchieu: getAfterLabel('Suất chiếu'),
            sove: getAfterLabel('Số vé bán ra|Số vé'),
          }, findLineValue: {
            doanhso: findLineValue('Doanh số'),
            suatchieu: findLineValue('Suất chiếu'),
            sove: findLineValue('Số vé bán ra'),
            release: findLineValue('Release date') || findLineValue('Khởi chiếu'),
          }};
        }
        """
    )
    body = data.get("body") or ""
    # prefer explicit labels
    revenue = None
    # "Doanh số 714,030,584,098₫"
    m = re.search(r"Doanh số\s*([0-9][0-9\.,\s]*₫|[0-9][0-9\.,\s]*(?:đ|vnđ)?)", body, flags=re.I)
    if m:
        revenue = clean_text(m.group(1))
    if not revenue:
        # sometimes total/cumulative phrasing
        m = re.search(r"(Tổng doanh thu|Doanh thu tích lũy)\s*[:\-]?\s*([0-9][0-9\.,\s]*(?:₫|đ|vnđ|tỷ|triệu)?)", body, flags=re.I)
        if m:
            revenue = clean_text(m.group(2))

    tickets = None
    m = re.search(r"Số vé(?: bán ra)?\s*([0-9][0-9\.,\s]*)", body, flags=re.I)
    if m:
        tickets = clean_text(m.group(1))
    screenings = None
    m = re.search(r"Suất chiếu\s*([0-9][0-9\.,\s]*)", body, flags=re.I)
    if m:
        screenings = clean_text(m.group(1))

    if _is_placeholder_metric(tickets):
        tickets = None
    if _is_placeholder_metric(screenings):
        screenings = None
    # revenue placeholders unlikely, but guard
    if revenue and _is_placeholder_metric(revenue.replace('₫','').replace('đ','')):
        revenue = None

    release = None
    m = re.search(r"(Release date|Khởi chiếu)\s*[:\-]?\s*([^\n]+)", body, flags=re.I)
    if m:
        release = clean_text(m.group(2))

    return {
        "bov_title": clean_text(data.get("title")),
        "revenue_bovn": revenue,
        "tickets_sold": tickets,
        "screening_count": screenings,
        "release_info": release,
        "raw_body_snippet": body[:2500],
    }
