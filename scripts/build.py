#!/usr/bin/env python3
"""
Parse data/<cycle>.md files into site/data.js for the static website.

Usage:  python scripts/build.py            (run from the repo root)
        python scripts/build.py --check    (parse only, exit 1 on hard errors)

Source format (one file per job-market cycle, e.g. data/2026-2027.md):

    ### 美国区域                              <- region header
    **[#1] Harvard（哈佛大学）**              <- school header (rank optional)
    **Name（中文名）**：他/她于2018年在...    <- candidate paragraph
    个人主页：https://...                     <- website (optional)
    **Placement: Assistant Professor, ...**  <- placement (optional)
    No Chinese in 2025-2026 Cycle.           <- free-text note under a school

See README.md for the full specification.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
FIELD_MAP_FILE = DATA_DIR / "fields.json"
REGION_MAP_FILE = DATA_DIR / "regions.json"
INSTITUTION_MAP_FILE = DATA_DIR / "institutions.json"
INDUSTRY_MAP_FILE = DATA_DIR / "industry.json"

# ---------------------------------------------------------------- regexes ---
RE_REGION = re.compile(r"^#{1,6}\s*(.+?)\s*$")
RE_SCHOOL = re.compile(
    r"^\*\*\s*(?:\[#\s*(?P<rank>[\d?]+)\s*\])?\s*(?P<name>[^（）*]+?)\s*(?:（(?P<zh>[^）]+)）)?\s*\*\*\s*$"
)
# candidate line: optional bold name, then a full-width or ascii colon, then the bio
RE_CANDIDATE = re.compile(r"^\*{0,2}\s*(?P<name>[^：:*]{1,80}?)\s*(?:\*\*)?\s*[：:]\s*(?:\*\*)?\s*(?P<bio>.*)$")
RE_WEBSITE = re.compile(r"^\*{0,2}\s*个人主页\s*[：:]\s*(?P<url>\S*)\s*\*{0,2}\s*$")
RE_PLACEMENT = re.compile(r"^\*{0,2}\s*(?:Placement|毕业去向)\s*[：:]\s*(?P<text>.*?)\s*\*{0,2}\s*$", re.I)
RE_NOTE = re.compile(r"^(No (Chinese|Econ)\b.*|TB Published\.?|TBD\.?|待更新.*)$", re.I)

RE_NAME_ZH = re.compile(r"^(?P<en>.*?)\s*[（(]\s*(?P<zh>[一-鿿·\s]+)\s*[)）]\s*$")
RE_EDU = re.compile(r"(?P<year>\d{4})年(?:在|于)?(?P<school>[^，。；、]+?)取得(?P<degree>[^，。；]+?)学位")
RE_PHD = re.compile(r"(?:预计将?于)?(?P<year>\d{4})年(?:在|于)?(?P<school>[^，。；]+?)取得(?P<degree>[^，。；]*?博士)学位")
RE_JMP_MARK = re.compile(r"JMP\s*(?:分别)?\s*(?:题为|题目为|标题为|为|:|：)\s*")
RE_QUOTED = re.compile(r"[“”\"「『]\s*(?P<t>[^“”\"「」『』]+?)\s*[“”\"」』]")
RE_FIELDS = re.compile(
    r"(?:研究(?:兴趣|领域|方向)(?:主要)?(?:包括|为|是|集中在|集中于|涵盖|涉及|聚焦于|聚焦|关注)?|主要关注|关注)"
    r"\s*[：:]?\s*(?P<f>.+?)(?=。|；|$|，\s*(?:她|他|其|合作|独立|单独|JMP|并|研究|论文|曾|已|目前|第[一二三四五]|[一两二三四五多数]篇|一作))"
)

QUOTE_CHARS = "“”\"「」『』"


def load_field_map() -> list[tuple[str, str]]:
    """Return ordered list of (keyword, category)."""
    raw = json.loads(FIELD_MAP_FILE.read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    for category, keywords in raw["categories"].items():
        for kw in keywords:
            pairs.append((kw, category))
    # longer keywords first so "国际贸易" wins over "贸易" etc.
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


KeywordMap = list[tuple[str, list[re.Pattern]]]


def load_keyword_map(path: Path, key: str) -> KeywordMap:
    """Return ordered list of (label, keyword patterns) from regions.json / institutions.json."""
    return load_keyword_map_from(json.loads(path.read_text(encoding="utf-8"))[key])


def load_industry_map() -> KeywordMap:
    """Return ordered list of ("sector|employer", keyword patterns) from industry.json."""
    raw = json.loads(INDUSTRY_MAP_FILE.read_text(encoding="utf-8"))
    flat = {f"{sector}|{employer}": kws for sector, employers in raw["sectors"].items() for employer, kws in employers.items()}
    return load_keyword_map_from(flat)


def load_keyword_map_from(mapping: dict[str, list[str]]) -> KeywordMap:
    return [
        (label, [re.compile(r"(?<![a-z])" + re.escape(kw.lower()) + r"(?![a-z])") for kw in keywords])
        for label, keywords in mapping.items()
    ]


def match_destination(text: str | None, kmap: KeywordMap) -> str | None:
    """First label whose keywords match the final destination in a placement text."""
    if not text:
        return None
    t = final_job(text)  # "Postdoc @ X, then AP @ Y" / "AP @ Y (after Postdoc @ X)" -> Y
    for label, patterns in kmap:
        if any(p.search(t) for p in patterns):
            return label
    return None


def split_name(name: str) -> tuple[str, str | None]:
    name = name.strip().strip("*").strip()
    m = RE_NAME_ZH.match(name)
    if m and m.group("en").strip():
        return m.group("en").strip(), m.group("zh").strip()
    return name, None


def parse_fields(bio: str, field_map: list[tuple[str, str]]) -> tuple[str | None, list[str]]:
    m = RE_FIELDS.search(bio)
    if not m:
        return None, []
    raw = m.group("f").strip()
    raw = re.sub(r"(等(领域|方向|问题|话题)?|领域|方向)\s*$", "", raw).strip()
    raw = re.sub(r"^(主要)?(集中在|集中于|包括|为|是)", "", raw).strip()
    tokens = [t.strip() for t in re.split(r"[、,，/]|\s+和\s*|(?<=[一-鿿])和(?=[一-鿿])|与|及|以及", raw) if t and t.strip()]
    cats: list[str] = []
    for tok in tokens:
        for kw, cat in field_map:
            if kw in tok and cat not in cats:
                cats.append(cat)
    return raw, cats


def parse_jmp(bio: str) -> str | None:
    m = RE_JMP_MARK.search(bio)
    if not m:
        return None
    rest = bio[m.end():]
    titles = [q.group("t").strip() for q in RE_QUOTED.finditer(rest)]
    if not rest.startswith(tuple(QUOTE_CHARS)):
        # missing opening quote: take text up to the first closing quote
        head = re.match(r"\s*(?P<t>[^“”\"「」『』。]+?)\s*[“”\"」』]", rest)
        if head:
            titles = [head.group("t").strip()] + titles[1:] if titles else [head.group("t").strip()]
    titles = [t for t in titles if t and not re.fullmatch(r"[\s。，,]*", t)]
    return " | ".join(titles) if titles else None


RE_NON_TENURE_TRACK = re.compile(
    r"of instruction|teaching (professor|faculty|track)|teaching-track|visiting (assistant |associate )?professor"
    r"|\bvap\b|clinical|adjunct|of practice|non-tenure|non tenure"
)


def final_job(text: str) -> str:
    """The destination itself: drop "(after Postdoc @ X)" and anything before "then"."""
    t = re.split(r"\bthen\b", text.lower())[-1]
    return re.sub(r"\(\s*after\b[^)]*\)", "", t)


def classify_placement(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower()
    # candidate went back on the market in a later cycle
    if re.search(r"延期|deferred", t):
        return "Deferred"
    # teaching / visiting / clinical positions are not tenure-track faculty
    if RE_NON_TENURE_TRACK.search(final_job(text)):
        return "Non-tenure-track"
    # faculty first: "Postdoc @ X, then AP @ Y" is ultimately a faculty placement
    if re.search(r"professor|\bap\b|lecturer|讲师|助理教授|副教授|教授|faculty|tenure", t):
        return "Faculty"
    if re.search(r"postdoc|post-doc|博士后|博后|research fellow|research associate|visiting scholar", t):
        return "Postdoc"
    return "Industry & Other"


def parse_file(path: Path, field_map: list[tuple[str, str]], region_map: KeywordMap, inst_map: KeywordMap,
               industry_map: KeywordMap, warnings: list[str]) -> dict:
    cycle = path.stem
    lines = path.read_text(encoding="utf-8").splitlines()

    region = None
    school = None
    schools: list[dict] = []
    candidates: list[dict] = []
    current: dict | None = None
    school_order = 0

    def warn(msg: str) -> None:
        warnings.append(f"{path.name}: {msg}")

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip().replace(" ", " ")
        if not line:
            continue

        m = RE_REGION.match(line)
        if m:
            region = m.group(1).strip("* ").strip()
            school = None
            current = None
            continue

        m = RE_SCHOOL.match(line)
        if m and "：" not in line and ":" not in line:
            school_order += 1
            rank_txt = m.group("rank")
            rank = int(rank_txt) if rank_txt and rank_txt.isdigit() else None
            school = {
                "cycle": cycle,
                "region": region or "未分区",
                "order": school_order,
                "rank": rank,
                "name": m.group("name").strip(),
                "name_zh": (m.group("zh") or "").strip() or None,
                # region + name disambiguates e.g. SMU (Southern Methodist) vs SMU (Singapore Management)
                "key": f"{region or '未分区'}|{m.group('name').strip()}",
                "notes": [],
                "n": 0,
            }
            schools.append(school)
            current = None
            continue

        m = RE_WEBSITE.match(line)
        if m:
            if current is None:
                warn(f"line {lineno}: 个人主页 without a preceding candidate")
                continue
            url = m.group("url").strip().rstrip("*").strip()
            current["website"] = url or None
            continue

        m = RE_PLACEMENT.match(line)
        if m:
            if current is None:
                warn(f"line {lineno}: Placement without a preceding candidate")
                continue
            current["placement"] = m.group("text").strip().strip("*").strip() or None
            continue

        if RE_NOTE.match(line):
            if school is not None:
                school["notes"].append(line)
            else:
                warn(f"line {lineno}: note outside of a school block: {line}")
            current = None
            continue

        m = RE_CANDIDATE.match(line)
        # A candidate line must not be a continuation of the previous bio: require
        # the name part to be short and not end in a sentence terminator.
        if m and not re.search(r"[。”\"]$", m.group("name")):
            if school is None:
                warn(f"line {lineno}: candidate before any school header: {line[:40]}")
                school = {
                    "cycle": cycle, "region": region or "未分区", "order": school_order,
                    "rank": None, "name": "未知院校", "name_zh": None, "key": f"{region or '未分区'}|未知院校", "notes": [], "n": 0,
                }
                schools.append(school)
            name_en, name_zh = split_name(m.group("name"))
            bio = m.group("bio").strip()
            current = {
                "cycle": cycle,
                "region": school["region"],
                "school": school["name"],
                "school_zh": school["name_zh"],
                "school_key": school["key"],
                "rank": school["rank"],
                "school_order": school["order"],
                "name": name_en,
                "name_zh": name_zh,
                "bio": bio,
                "website": None,
                "placement": None,
                "line": lineno,
            }
            candidates.append(current)
            school["n"] += 1
            continue

        # Otherwise: continuation of the previous bio paragraph (wrapped line)
        if current is not None:
            current["bio"] = (current["bio"] + " " + line).strip() if current["bio"] else line
        else:
            warn(f"line {lineno}: unrecognised line ignored: {line[:60]}")

    # ---- derive structured fields from each bio
    for c in candidates:
        bio = c["bio"]
        c["info_missing"] = (not bio) or ("信息不详" in bio)
        pm = re.search(r"[他她]", bio)
        c["gender"] = None if not pm else ("F" if pm.group(0) == "她" else "M")

        edu = []
        for m in RE_EDU.finditer(bio):
            edu.append({"year": int(m.group("year")), "school": m.group("school").strip(), "degree": m.group("degree").strip()})
        c["education"] = edu

        phd = None
        for m in RE_PHD.finditer(bio):
            phd = {"year": int(m.group("year")), "school": m.group("school").strip(), "degree": m.group("degree").strip()}
        c["phd_year"] = phd["year"] if phd else None

        c["jmp"] = parse_jmp(bio)

        c["fields_raw"], c["fields"] = parse_fields(bio, field_map)
        c["placement_type"] = classify_placement(c["placement"])
        academic = c["placement_type"] in ("Faculty", "Non-tenure-track")
        c["placement_region"] = match_destination(c["placement"], region_map) if academic else None
        c["placement_inst"] = match_destination(c["placement"], inst_map) if academic else None
        # a bare "Lecturer" is tenure-track in the UK / Australia / NZ but teaching-track in the US / Canada
        job = final_job(c["placement"] or "")
        if (c["placement_type"] == "Faculty" and re.search(r"lecturer|讲师", job)
                and not re.search(r"professor|\bap\b|senior lecturer", job)
                and c["placement_region"] in ("美国", "加拿大")):
            c["placement_type"] = "Non-tenure-track"
        # industry placements: "sector|employer" -> sector, employer; unmatched ones count as 其他
        hit = match_destination(c["placement"], industry_map) if c["placement_type"] == "Industry & Other" else None
        c["placement_sector"], c["placement_employer"] = hit.split("|", 1) if hit else (None, None)

        slug = re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-") or "x"
        c["id"] = f"{cycle}/{slug}"
        del c["line"]

    return {"cycle": cycle, "schools": schools, "candidates": candidates}


def main() -> int:
    check_only = "--check" in sys.argv
    field_map = load_field_map()
    region_map = load_keyword_map(REGION_MAP_FILE, "regions")
    inst_map = load_keyword_map(INSTITUTION_MAP_FILE, "institutions")
    industry_map = load_industry_map()
    warnings: list[str] = []

    files = sorted(DATA_DIR.glob("*.md"))
    files = [f for f in files if not f.name.startswith("_")]
    if not files:
        print("No data/*.md files found", file=sys.stderr)
        return 1

    cycles = []
    all_candidates = []
    all_schools = []
    for f in files:
        parsed = parse_file(f, field_map, region_map, inst_map, industry_map, warnings)
        cycles.append(parsed["cycle"])
        all_candidates.extend(parsed["candidates"])
        all_schools.extend(parsed["schools"])
        n = len(parsed["candidates"])
        n_placed = sum(1 for c in parsed["candidates"] if c["placement"])
        print(f"{f.name}: {len(parsed['schools'])} schools, {n} candidates, {n_placed} with placement")

    # report tokens that were not mapped to a field category (helps refine fields.json)
    unmapped: dict[str, int] = {}
    for c in all_candidates:
        if c["fields_raw"] and not c["fields"]:
            unmapped[c["fields_raw"]] = unmapped.get(c["fields_raw"], 0) + 1
    if unmapped:
        print(f"\n{len(unmapped)} research-interest strings had no category match (add keywords to data/fields.json):")
        for k, v in sorted(unmapped.items(), key=lambda kv: -kv[1])[:30]:
            print(f"   {v:3d}  {k}")

    # faculty placements whose institution is not in regions.json
    no_region = [c for c in all_candidates if c["placement_type"] in ("Faculty", "Non-tenure-track") and not c["placement_region"]]
    if no_region:
        print(f"\n{len(no_region)} faculty placements had no region match (add keywords to data/regions.json):")
        for c in no_region:
            print(f"   {c['cycle']}  {c['placement']}")
    no_inst = [c for c in all_candidates if c["placement_type"] == "Faculty" and not c["placement_inst"]]
    if no_inst:
        print(f"\n{len(no_inst)} faculty placements had no institution match (add keywords to data/institutions.json):")
        for c in no_inst:
            print(f"   {c['cycle']}  {c['placement']}")

    no_sector = [c for c in all_candidates if c["placement_type"] == "Industry & Other" and not c["placement_sector"]]
    if no_sector:
        print(f"\n{len(no_sector)} industry placements counted as 其他 (add employers to data/industry.json if they fit a sector):")
        for c in no_sector:
            print(f"   {c['cycle']}  {c['placement']}")

    if warnings:
        print(f"\n{len(warnings)} warnings:")
        for w in warnings:
            print("   " + w)

    if check_only:
        return 0

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "cycles": sorted(cycles, reverse=True),
        "field_categories": list(json.loads(FIELD_MAP_FILE.read_text(encoding="utf-8"))["categories"].keys()),
        "placement_regions": [region for region, _ in region_map],
        "schools": all_schools,
        "candidates": all_candidates,
    }
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out = SITE_DIR / "data.js"
    out.write_text("window.JMC_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (SITE_DIR / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWrote {out} ({out.stat().st_size // 1024} KB), {len(all_candidates)} candidates in {len(cycles)} cycles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
