from __future__ import annotations

import asyncio
import json
import random
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from .config import REQUEST_DELAY_MAX, REQUEST_DELAY_MIN, RETRY_BACKOFF, RETRY_COUNT

T = TypeVar("T")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


async def polite_delay(min_s: float = REQUEST_DELAY_MIN, max_s: float = REQUEST_DELAY_MAX) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def with_retry(
    func: Callable[[], Any],
    retries: int = RETRY_COUNT,
    base_backoff: float = RETRY_BACKOFF,
    label: str = "operation",
):
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retries:
                break
            wait = base_backoff ** (attempt - 1)
            print(f"[retry] {label} attempt {attempt}/{retries} failed: {exc}; sleeping {wait:.1f}s")
            await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", text)


def normalize_title(text: str | None) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    t = strip_accents(t)
    # normalize d/d with stroke variants
    t = t.replace("đ", "d")
    t = t.replace("&", " and ")
    # normalize numeric vs word forms ("Heo 5 Móng" == "Heo Năm Móng")
    digit_words = {
        "0": "khong",
        "1": "mot",
        "2": "hai",
        "3": "ba",
        "4": "bon",
        "5": "nam",
        "6": "sau",
        "7": "bay",
        "8": "tam",
        "9": "chin",
        "10": "muoi",
    }
    t = re.sub(r"\b(10|[0-9])\b", lambda m: digit_words.get(m.group(1), m.group(1)), t)
    t = re.sub(r"[\(\)\[\]\{\}:;,.!?\"'`~@#$%^*_+=/\\|<>-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def parse_int_like(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def parse_money_vnd(value: str | None) -> int | None:
    """Parse VND-like strings into integer VND when possible."""
    if not value:
        return None
    s = value.lower().replace("\xa0", " ").strip()
    if not s or s in {"-", "n/a", "na", "đang cập nhật"}:
        return None
    # extract number and unit
    m = re.search(r"([0-9][0-9\.,\s]*)", s)
    if not m:
        return None
    num_str = m.group(1).strip().replace(" ", "")
    # handle Vietnamese decimal/comma formats heuristically
    # prefer removing thousand separators
    if num_str.count(",") > 0 and num_str.count(".") > 0:
        # assume last separator is decimal if followed by 1-2 digits, else thousands
        if re.search(r"[\.,]\d{1,2}$", num_str):
            num_str = num_str.replace(".", "").replace(",", ".")
        else:
            num_str = num_str.replace(".", "").replace(",", "")
    elif num_str.count(",") == 1 and re.search(r",\d{1,2}$", num_str):
        num_str = num_str.replace(",", ".")
    else:
        num_str = num_str.replace(",", "").replace(".", "")
    try:
        num = float(num_str)
    except ValueError:
        return None
    unit = s[m.end():]
    mult = 1
    if "tỷ" in unit or "ty" in unit:
        mult = 1_000_000_000
    elif "triệu" in unit or "trieu" in unit or "mn" in unit:
        mult = 1_000_000
    elif "nghìn" in unit or "nghin" in unit or "k" in unit:
        mult = 1_000
    elif "đ" in unit or "vnd" in unit:
        mult = 1
    return int(round(num * mult))


def split_titles(raw: str | None) -> tuple[str | None, str | None]:
    """Try to split Vietnamese/English or alternate titles from one string."""
    if not raw:
        return None, None
    s = raw.strip()
    # common separators: " / ", " - ", " | ", parentheses with alternate title
    for sep in [" / ", " | "]:
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if len(parts) >= 2:
                return parts[0], parts[1]
    # pattern: Vietnamese (English)
    m = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", s)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        # avoid year-only parentheses
        if a and b and not re.fullmatch(r"\d{4}", b):
            return a, b
    return s, None
