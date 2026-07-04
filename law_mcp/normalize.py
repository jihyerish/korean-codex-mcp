from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin


LAW_GO_KR_BASE_URL = "https://www.law.go.kr"

SEARCH_ITEM_KEYS = {
    "law": "law",
    "eflaw": "law",
    "admrul": "admrul",
    "ordin": "ordin",
}

DETAIL_TARGET_LABELS = {
    "law": "law",
    "eflaw": "law",
    "admrul": "administrative_rule",
    "ordin": "local_ordinance",
}

TEXT_KEYS = {
    "조문내용",
    "항내용",
    "호내용",
    "목내용",
    "부칙내용",
    "별표내용",
    "제개정문내용",
    "개정문내용",
    "이유내용",
}

ARTICLE_MARKER_KEYS = {"조문번호", "조문가지번호", "조문제목", "조문내용"}


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return text


def first_value(data: Any, keys: list[str]) -> str | None:
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            text = clean_text(value)
            if text:
                return text
        for value in data.values():
            found = first_value(value, keys)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = first_value(item, keys)
            if found:
                return found
    return None


def absolute_law_url(link: Any) -> str | None:
    text = clean_text(link)
    if not text:
        return None
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return urljoin(LAW_GO_KR_BASE_URL, text)


def extract_root(parsed_xml: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if len(parsed_xml) == 1:
        name, body = next(iter(parsed_xml.items()))
        if isinstance(body, dict):
            return name, body
    return "root", parsed_xml


def extract_search_items(body: dict[str, Any], target: str) -> list[dict[str, Any]]:
    preferred_key = SEARCH_ITEM_KEYS.get(target, target)
    items = ensure_list(body.get(preferred_key))
    if items:
        return [item for item in items if isinstance(item, dict)]

    metadata_keys = {
        "target",
        "query",
        "키워드",
        "section",
        "totalCnt",
        "page",
        "display",
        "numOfRows",
    }
    for key, value in body.items():
        if key in metadata_keys:
            continue
        candidates = ensure_list(value)
        if candidates and all(isinstance(item, dict) for item in candidates):
            return candidates
    return []


def normalize_search_item(item: dict[str, Any]) -> dict[str, Any]:
    detail_link = first_value(
        item,
        [
            "법령상세링크",
            "행정규칙상세링크",
            "자치법규상세링크",
            "상세링크",
            "link",
        ],
    )
    title = first_value(
        item,
        [
            "법령명한글",
            "법령명",
            "행정규칙명",
            "자치법규명",
            "법령약칭명",
            "제목",
        ],
    )
    mst = first_value(
        item,
        [
            "법령일련번호",
            "행정규칙일련번호",
            "자치법규일련번호",
            "MST",
            "mst",
            "일련번호",
        ],
    )
    document_id = first_value(
        item,
        [
            "법령ID",
            "행정규칙ID",
            "자치법규ID",
            "ID",
            "id",
        ],
    )

    return {
        "title": title,
        "mst": mst,
        "id": document_id,
        "document_key": mst or document_id,
        "key_type": "mst" if mst else "id" if document_id else None,
        "type": first_value(item, ["법령구분명", "행정규칙종류명", "자치법규종류명"]),
        "ministry": first_value(item, ["소관부처명", "소관부처", "소관기관명"]),
        "promulgation_date": compact_date(first_value(item, ["공포일자", "발령일자"])),
        "effective_date": compact_date(first_value(item, ["시행일자", "시행일"])),
        "revision_type": first_value(item, ["제개정구분명", "제개정구분"]),
        "detail_url": absolute_law_url(detail_link),
        "raw": item,
    }


def normalize_search_response(
    parsed_xml: dict[str, Any],
    target: str,
    query: str,
    page: int,
    limit: int,
) -> dict[str, Any]:
    root_name, body = extract_root(parsed_xml)
    items = [normalize_search_item(item) for item in extract_search_items(body, target)]
    total = first_value(body, ["totalCnt", "totalCount", "total", "전체건수"])

    return {
        "query": query,
        "target": target,
        "root": root_name,
        "page": page,
        "limit": limit,
        "total_count": int(total) if total and total.isdigit() else total,
        "items": items,
    }


def collect_text_parts(node: Any, parts: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in TEXT_KEYS:
                text = clean_text(value)
                if text:
                    parts.append(text)
            else:
                collect_text_parts(value, parts)
    elif isinstance(node, list):
        for item in node:
            collect_text_parts(item, parts)


def article_number(node: dict[str, Any]) -> str | None:
    number = clean_text(node.get("조문번호"))
    branch = clean_text(node.get("조문가지번호"))
    if not number:
        return None
    try:
        number_text = str(int(number))
    except ValueError:
        number_text = number
    if branch and branch not in {"0", "00", "000"}:
        try:
            branch_text = str(int(branch))
        except ValueError:
            branch_text = branch
        return f"제{number_text}조의{branch_text}"
    return f"제{number_text}조"


def normalize_article(node: dict[str, Any]) -> dict[str, Any]:
    parts: list[str] = []
    collect_text_parts(node, parts)
    content = "\n".join(dict.fromkeys(part for part in parts if part))
    title = clean_text(node.get("조문제목"))
    number = article_number(node)
    label = number or title or "article"
    if title and number:
        label = f"{number}({title})"

    return {
        "article_number": number,
        "title": title or None,
        "label": label,
        "effective_date": compact_date(node.get("조문시행일자")),
        "content": content,
    }


def collect_articles(node: Any, articles: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        if ARTICLE_MARKER_KEYS.intersection(node.keys()) and clean_text(node.get("조문내용")):
            normalized = normalize_article(node)
            if normalized["content"]:
                articles.append(normalized)
            return
        for value in node.values():
            collect_articles(value, articles)
    elif isinstance(node, list):
        for item in node:
            collect_articles(item, articles)


def unique_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str | None, str]] = set()
    result: list[dict[str, Any]] = []
    for article in articles:
        marker = (article.get("article_number"), article.get("content", "")[:100])
        if marker in seen:
            continue
        seen.add(marker)
        result.append(article)
    return result


def normalize_detail_response(parsed_xml: dict[str, Any], target: str) -> dict[str, Any]:
    root_name, body = extract_root(parsed_xml)
    articles: list[dict[str, Any]] = []
    collect_articles(body, articles)

    return {
        "target": target,
        "document_type": DETAIL_TARGET_LABELS.get(target, target),
        "root": root_name,
        "title": first_value(
            body,
            [
                "법령명_한글",
                "법령명한글",
                "법령명",
                "행정규칙명",
                "자치법규명",
                "공포법령명",
            ],
        ),
        "mst": first_value(body, ["법령일련번호", "행정규칙일련번호", "자치법규일련번호"]),
        "id": first_value(body, ["법령ID", "행정규칙ID", "자치법규ID"]),
        "ministry": first_value(body, ["소관부처", "소관부처명", "소관기관명"]),
        "promulgation_date": compact_date(first_value(body, ["공포일자", "발령일자"])),
        "effective_date": compact_date(first_value(body, ["시행일자", "시행일"])),
        "articles": unique_articles(articles),
        "raw": body,
    }


def score_text(query: str, text: str) -> int:
    normalized_text = text.lower()
    terms = [term for term in re.split(r"\s+", query.lower()) if len(term) >= 2]
    if not terms:
        return 0
    score = 0
    for term in terms:
        if term in normalized_text:
            score += 5
        score += normalized_text.count(term)
    return score


def filter_articles(
    articles: list[dict[str, Any]],
    query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not query:
        return articles[:limit]

    scored: list[tuple[int, dict[str, Any]]] = []
    for article in articles:
        haystack = " ".join(
            clean_text(article.get(key))
            for key in ("label", "title", "content")
            if article.get(key)
        )
        scored.append((score_text(query, haystack), article))

    matches = [article for score, article in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]
    if matches:
        return matches[:limit]
    return articles[:limit]


def trim_article(article: dict[str, Any], max_chars: int = 1200) -> dict[str, Any]:
    content = clean_text(article.get("content"))
    if len(content) > max_chars:
        content = content[: max_chars - 1].rstrip() + "..."
    return {
        "article_number": article.get("article_number"),
        "title": article.get("title"),
        "label": article.get("label"),
        "effective_date": article.get("effective_date"),
        "content": content,
    }

