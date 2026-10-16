#!/usr/bin/env python3
"""
Download each candidate's homepage (plus same-site Research / Papers / CV-like
subpages) and save the visible text to cache/pages/<key>.txt, for building
data/research.json.

Usage:  python scripts/fetch_homepages.py [--cycle 2026-2027] [--force]
Requires site/data.json (run scripts/build.py first).
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "pages"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
SUB_RE = re.compile(r"research|paper|publication|working|work|cv|vita", re.I)


def cand_key(c: dict) -> str:
    """Stable key for a candidate: cycle|school|name (ids from build.py can collide)."""
    return f"{c['cycle']}|{c['school']}|{c['name']}"


def file_stem(key: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", key).strip("-")[:60]
    return f"{slug}-{hashlib.md5(key.encode()).hexdigest()[:6]}"


def get(url: str) -> tuple[str, str] | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25, allow_redirects=True)
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
            return None
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        return r.url, r.text
    except requests.RequestException:
        return None


def visible_text(html: str) -> tuple[str, BeautifulSoup]:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg", "header nav"]):
        t.decompose()
    # keep link targets for papers (journal names / SSRN links help classification)
    text = soup.get_text("\n")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text, soup


def fetch_one(c: dict, force: bool) -> tuple[str, str]:
    key = cand_key(c)
    out = CACHE / (file_stem(key) + ".txt")
    if out.exists() and not force:
        return key, "cached"
    res = get(c["website"])
    if not res:
        out.write_text(f"KEY: {key}\nURL: {c['website']}\nFETCH_FAILED\n", encoding="utf-8")
        return key, "failed"
    final_url, html = res
    text, soup = visible_text(html)
    parts = [f"=== PAGE {final_url}\n{text}"]
    host = urlparse(final_url).netloc
    seen = {final_url.rstrip("/")}
    subs = []
    for a in soup.find_all("a", href=True):
        href = urljoin(final_url, a["href"]).split("#")[0]
        label = (a.get_text(" ", strip=True) or "") + " " + href
        if urlparse(href).netloc != host or href.rstrip("/") in seen or href.lower().endswith(".pdf"):
            continue
        if SUB_RE.search(label):
            seen.add(href.rstrip("/"))
            subs.append(href)
    for href in subs[:4]:
        r = get(href)
        if r:
            parts.append(f"=== PAGE {r[0]}\n{visible_text(r[1])[0]}")
    body = "\n\n".join(parts)[:60000]
    out.write_text(f"KEY: {key}\nURL: {c['website']}\n{body}\n", encoding="utf-8")
    return key, f"ok ({len(parts)} pages)"


def main() -> int:
    force = "--force" in sys.argv
    cyc = sys.argv[sys.argv.index("--cycle") + 1] if "--cycle" in sys.argv else None
    data = json.loads((ROOT / "site" / "data.json").read_text(encoding="utf-8"))
    cands = [c for c in data["candidates"] if c.get("website") and (not cyc or c["cycle"] == cyc)]
    CACHE.mkdir(parents=True, exist_ok=True)
    index = {}
    with cf.ThreadPoolExecutor(12) as ex:
        futs = {ex.submit(fetch_one, c, force): c for c in cands}
        for f in cf.as_completed(futs):
            c = futs[f]
            key, status = f.result()
            index[key] = {"file": file_stem(key) + ".txt", "url": c["website"], "status": status}
            print(f"{status:14s} {key}")
    (CACHE.parent / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(cands)} candidates; failed: {sum(1 for v in index.values() if v['status'] == 'failed')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
