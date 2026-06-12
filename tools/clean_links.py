#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

import requests


URL_TIMEOUT = 5
MAX_WORKERS = 24
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)


CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("搜索源", ["搜索", "search", "searx", "yandex", "kagi", "presearch", "sogou", "识图", "找资源", "检索"]),
    ("AI工具", ["AI", "gpt", "claude", "gemini", "gemma", "agent", "模型", "提示词", "aigc"]),
    ("学习资料", ["学习", "课程", "考试", "备考", "考公", "软考", "教材", "资料库", "公开课"]),
    ("软件工具", ["工具", "软件", "app", "windows", "mac", "插件", "脚本", "增强", "下载器", "github"]),
    ("设计素材", ["设计", "图片", "图标", "字体", "素材", "封面", "模板", "mockup", "图表", "截图"]),
    ("影音娱乐", ["电影", "美剧", "字幕", "音乐", "游戏", "steam", "动漫", "视频"]),
    ("网盘资源", ["网盘", "夸克", "阿里云盘", "百度网盘", "迅雷", "lanzou", "pan.", "ysepan", "123pan"]),
    ("文档知识库", ["flowus", "飞书", "语雀", "notion", "kdocs", "docs.", "wiki", "文档"]),
    ("教程文章", ["教程", "指南", "怎么", "如何", "零基础", "技巧", "解决方法"]),
    ("运营页面", ["售后", "反馈", "意见征集", "用户协议", "发展历程", "加群", "客服"]),
]

DOMAIN_CATEGORY_HINTS = {
    "github.com": "软件工具",
    "pan.quark.cn": "网盘资源",
    "pan.baidu.com": "网盘资源",
    "aliyundrive.com": "网盘资源",
    "alipan.com": "网盘资源",
    "flowus.cn": "文档知识库",
    "yuque.com": "文档知识库",
    "kdocs.cn": "文档知识库",
    "bilibili.com": "影音娱乐",
    "b23.tv": "影音娱乐",
}

DROP_OR_REVIEW_KEYWORDS = [
    "专属售后群",
    "意见征集",
    "资源失效反馈",
    "用户协议",
    "发展历程",
    "网站打不开",
]

SHORTENER_DOMAINS = {
    "b23.tv",
    "bit.ly",
    "t.co",
    "tinyurl.com",
    "goo.gl",
    "is.gd",
}

TRACKING_PARAMS_PREFIXES = ("utm_",)
TRACKING_PARAMS = {
    "ref",
    "from",
    "source",
    "spm",
    "hmsr",
    "rel",
    "imyshare.com",
    "ysclid",
}


@dataclass
class LinkRecord:
    id: str
    page: int
    source: str
    title: str
    original_title: str
    url: str
    normalized_url: str
    domain: str
    category: str
    tags: list[str]
    score: int
    tier: str
    is_free: bool
    status: str
    http_status: int | None
    final_url: str | None
    notes: list[str]


def clean_title(title: str) -> str:
    title = title.replace("\u200b", "")
    title = re.sub(r"\s+", " ", title)
    title = title.strip(" \t\r\n丨|_-—")
    replacements = {
        "Ai ": "AI ",
        "ai": "AI",
        "yadex": "Yandex",
        "yandex": "Yandex",
        "github": "GitHub",
        "vx": "微信",
    }
    for old, new in replacements.items():
        title = title.replace(old, new)
    return title


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or ""
    query = parse_qs(parsed.query, keep_blank_values=True)
    kept = []
    for key in sorted(query):
        key_lower = key.lower()
        if key_lower in TRACKING_PARAMS or any(key_lower.startswith(prefix) for prefix in TRACKING_PARAMS_PREFIXES):
            continue
        for value in query[key]:
            kept.append((key, value))
    query_text = "&".join(f"{key}={value}" if value else key for key, value in kept)
    result = f"{scheme}://{netloc}{path}"
    if query_text:
        result += f"?{query_text}"
    if parsed.fragment:
        result += f"#{parsed.fragment}"
    return result


def classify(title: str, url: str, domain: str) -> tuple[str, list[str]]:
    text = f"{title} {url} {domain}"
    text_lower = text.lower()
    tags: list[str] = []

    if domain in DOMAIN_CATEGORY_HINTS:
        category = DOMAIN_CATEGORY_HINTS[domain]
    else:
        category = "未分类"

    for candidate, keywords in CATEGORY_RULES:
        if any(contains_keyword(text, keyword) for keyword in keywords):
            category = candidate
            break

    tag_rules = {
        "搜索": ["搜索", "search", "searx", "Yandex"],
        "AI": ["AI", "gpt", "claude", "gemma", "aigc"],
        "网盘": ["网盘", "pan.", "夸克", "百度网盘", "迅雷", "ysepan"],
        "开源": ["github", "开源"],
        "教程": ["教程", "指南", "技巧"],
        "设计": ["设计", "图片", "图标", "素材", "模板"],
        "文档": ["flowus", "kdocs", "语雀", "飞书", "notion"],
    }
    for tag, keywords in tag_rules.items():
        if any(contains_keyword(text, keyword) for keyword in keywords):
            tags.append(tag)

    return category, tags


def contains_keyword(text: str, keyword: str) -> bool:
    if keyword == "AI":
        return re.search(r"(?i)(^|[^a-z])ai([^a-z]|$)", text) is not None
    return keyword.lower() in text.lower()


def validate_url(url: str) -> tuple[str, int | None, str | None, list[str]]:
    notes: list[str] = []
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    try:
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=URL_TIMEOUT)
        if response.status_code in {403, 405, 429} or response.status_code >= 500:
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=URL_TIMEOUT, stream=True)
        status = response.status_code
        final_url = response.url
        if final_url and final_url != url:
            notes.append("redirect")
        if 200 <= status < 400:
            return "ok", status, final_url, notes
        if status in {401, 403}:
            return "restricted", status, final_url, notes
        if status == 404:
            return "missing", status, final_url, notes
        return "error", status, final_url, notes
    except requests.Timeout:
        return "timeout", None, None, ["timeout"]
    except requests.RequestException as exc:
        return "error", None, None, [exc.__class__.__name__]


def score_record(title: str, url: str, domain: str, category: str, status: str, notes: list[str]) -> int:
    score = 50
    if status == "ok":
        score += 25
    elif status == "restricted":
        score += 8
    elif status == "timeout":
        score -= 8
    else:
        score -= 20

    if url.startswith("https://"):
        score += 5
    else:
        score -= 5

    if len(title) >= 6:
        score += 8
    if len(title) <= 1 or title in {"a", "等"}:
        score -= 25

    if category in {"搜索源", "AI工具", "软件工具", "学习资料", "设计素材"}:
        score += 8
    if category == "运营页面":
        score -= 35
    if domain in SHORTENER_DOMAINS:
        score -= 6
    if domain.endswith("pdfjm.top"):
        score -= 18
    if "redirect" in notes:
        score -= 2

    return max(0, min(100, score))


def choose_tier(
    category: str,
    score: int,
    title: str,
    domain: str,
    url: str,
    duplicate_index: int,
) -> tuple[str, bool, list[str]]:
    notes: list[str] = []
    text = f"{title} {domain} {url}"

    if any(keyword in text for keyword in DROP_OR_REVIEW_KEYWORDS):
        notes.append("owner_or_operations_page")
        return "review", False, notes

    if domain.endswith("pdfjm.top") or "galijun" in text.lower():
        notes.append("source_owner_related")
        return "paid", False, notes

    if category == "运营页面":
        notes.append("operations_page")
        return "review", False, notes

    if category == "网盘资源" or any(marker in domain for marker in ("pan.", "lanzou", "ysepan")):
        notes.append("direct_resource_link")
        return "paid", False, notes

    if score < 45:
        notes.append("low_score")
        return "review", False, notes

    if duplicate_index > 1:
        notes.append("duplicate_url")

    public_categories = {"搜索源", "AI工具", "软件工具", "设计素材", "教程文章"}
    if category in public_categories and score >= 80 and duplicate_index == 1:
        return "free", True, notes

    if category == "学习资料" and score >= 85 and duplicate_index == 1:
        return "free", True, notes

    return "paid", False, notes


def stable_id(url: str, title: str) -> str:
    return hashlib.sha1(f"{url}\n{title}".encode("utf-8")).hexdigest()[:12]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file, delimiter="\t"))


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_tsv(path: Path, records: Iterable[LinkRecord]) -> None:
    rows = [asdict(record) for record in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        if not rows:
            return
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        for row in rows:
            row["tags"] = ",".join(row["tags"])
            row["notes"] = ",".join(row["notes"])
            writer.writerow(row)


def process(input_path: Path, output_dir: Path, validate: bool) -> None:
    raw_rows = read_rows(input_path)
    prepared = []
    for row in raw_rows:
        url = row["url"].strip()
        normalized = normalize_url(url)
        title = clean_title(row["label"])
        domain = domain_of(normalized)
        category, tags = classify(title, normalized, domain)
        prepared.append((row, title, normalized, domain, category, tags))

    validation: dict[str, tuple[str, int | None, str | None, list[str]]] = load_validation_cache(output_dir)
    urls = sorted({item[2] for item in prepared})
    if validate:
        missing_urls = [url for url in urls if url not in validation]
        print(f"validating {len(missing_urls)} new urls; using cache for {len(urls) - len(missing_urls)} urls...")
        if missing_urls:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_map = {executor.submit(validate_url, url): url for url in missing_urls}
                done = 0
                started = time.time()
                for future in as_completed(future_map):
                    url = future_map[future]
                    validation[url] = future.result()
                    done += 1
                    if done % 100 == 0:
                        print(f"validated {done}/{len(missing_urls)} in {time.time() - started:.1f}s")
    else:
        validation = {url: ("unknown", None, None, []) for url in urls}

    duplicate_counts: dict[str, int] = {}
    records: list[LinkRecord] = []
    for row, title, normalized, domain, category, tags in prepared:
        duplicate_counts[normalized] = duplicate_counts.get(normalized, 0) + 1
        duplicate_index = duplicate_counts[normalized]
        status, http_status, final_url, validation_notes = validation[normalized]
        notes = list(validation_notes)
        score = score_record(title, normalized, domain, category, status, notes)
        tier, is_free, tier_notes = choose_tier(category, score, title, domain, normalized, duplicate_index)
        notes.extend(tier_notes)
        record = LinkRecord(
            id=stable_id(normalized, title),
            page=int(row["page"]),
            source=row["source"],
            title=title,
            original_title=row["label"],
            url=row["url"],
            normalized_url=normalized,
            domain=domain,
            category=category,
            tags=tags,
            score=score,
            tier=tier,
            is_free=is_free,
            status=status,
            http_status=http_status,
            final_url=final_url,
            notes=notes,
        )
        records.append(record)

    full_records = records
    free_records = [record for record in records if record.is_free]
    review_records = [record for record in records if record.tier == "review" or record.score < 55]

    write_json(output_dir / "links.full.json", [asdict(record) for record in full_records])
    write_json(output_dir / "links.free.json", [asdict(record) for record in free_records])
    write_json(output_dir / "links.review.json", [asdict(record) for record in review_records])
    write_tsv(output_dir / "links.full.tsv", full_records)
    write_tsv(output_dir / "links.free.tsv", free_records)
    write_tsv(output_dir / "links.review.tsv", review_records)

    summary = {
        "input": str(input_path),
        "total_rows": len(records),
        "unique_urls": len({record.normalized_url for record in records}),
        "free_rows": len(free_records),
        "paid_rows": len([record for record in records if record.tier == "paid"]),
        "review_rows": len(review_records),
        "by_category": count_by(records, "category"),
        "by_status": count_by(records, "status"),
        "by_tier": count_by(records, "tier"),
        "top_domains": top_domains(records),
    }
    write_json(output_dir / "summary.json", summary)
    write_site_data(records, output_dir.parent / "site" / "src" / "data", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_site_data(records: list[LinkRecord], site_data_dir: Path, summary: dict[str, object]) -> None:
    excluded_note_markers = {"owner_or_operations_page", "source_owner_related", "operations_page"}

    def visible(record: LinkRecord) -> bool:
        if any(note in excluded_note_markers for note in record.notes):
            return False
        return True

    site_records = [record for record in records if visible(record)]
    site_records.sort(key=lambda record: (record.category, -record.score, record.page, record.title))

    public_links = [
        {
            "id": record.id,
            "title": record.title,
            "url": record.normalized_url,
            "domain": record.domain,
            "category": record.category,
            "tags": record.tags,
            "score": record.score,
            "page": record.page,
            "status": record.status,
            "notes": record.notes,
        }
        for record in site_records
    ]

    clean_records = [
        record
        for record in records
        if not any(note in excluded_note_markers for note in record.notes)
    ]
    categories = count_by(clean_records, "category")
    public_categories = count_by(site_records, "category")
    site_stats = {
        "generatedFrom": "output.links.txt",
        "publicCount": len(public_links),
        "totalCleanCount": len(clean_records),
        "fullCount": len(records),
        "paidPreviewCount": len([record for record in clean_records if record.tier == "paid"]),
        "reviewCount": len([record for record in clean_records if record.tier == "review" or record.score < 55]),
        "categories": categories,
        "publicCategories": public_categories,
        "status": count_by(clean_records, "status"),
        "topDomains": top_domains(clean_records, 20),
        "mode": "full_static_public",
        "contactSlots": {
            "wechatQr": "",
            "wechatGroupImage": "",
            "telegram": "",
            "email": "",
        },
    }

    write_json(site_data_dir / "links.json", public_links)
    write_json(site_data_dir / "stats.json", site_stats)


def load_validation_cache(output_dir: Path) -> dict[str, tuple[str, int | None, str | None, list[str]]]:
    cache_path = output_dir / "links.full.json"
    if not cache_path.exists():
        return {}
    try:
        records = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    cache = {}
    for record in records:
        url = record.get("normalized_url")
        if not url:
            continue
        cache[url] = (
            record.get("status") or "unknown",
            record.get("http_status"),
            record.get("final_url"),
            [
                note
                for note in record.get("notes", [])
                if note in {"timeout", "redirect", "ConnectionError", "SSLError", "TooManyRedirects"}
            ],
        )
    return cache


def count_by(records: list[LinkRecord], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(getattr(record, field))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def top_domains(records: list[LinkRecord], limit: int = 30) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.domain] = counts.get(record.domain, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean, classify, validate, and split PDF-extracted links.")
    parser.add_argument("--input", default="output.links.txt", help="Input TSV from pdfjm_decrypt.py.")
    parser.add_argument("--output-dir", default="data", help="Directory for generated datasets.")
    parser.add_argument("--no-validate", action="store_true", help="Skip HTTP validation.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    process(Path(args.input), Path(args.output_dir), validate=not args.no_validate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
