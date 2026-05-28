import re


SECTION_TITLES = (
    "已确认问题",
    "待关注风险",
    "调查摘要",
    "证据与判断依据",
    "评分明细",
    "建议",
    "风险等级",
)


def _split_sections(review_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_title: str | None = None
    current_lines: list[str] = []

    def flush_current_section():
        if current_title is not None:
            sections[current_title] = "\n".join(current_lines).strip()

    for raw_line in (review_text or "").splitlines():
        stripped = raw_line.strip()
        matched_title = None
        matched_inline = ""
        for title in SECTION_TITLES:
            match = re.match(rf"^{re.escape(title)}(?:[:：]\s*(.*))?$", stripped)
            if match:
                matched_title = title
                matched_inline = (match.group(1) or "").strip()
                break

        if matched_title is not None:
            flush_current_section()
            current_title = matched_title
            current_lines = [matched_inline] if matched_inline else []
            continue

        if current_title is not None:
            current_lines.append(raw_line)

    flush_current_section()
    return sections


def _parse_bullet_lines(section_text: str) -> list[str]:
    items: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s*", "", line)
        if line:
            items.append(line)
    return items


def _parse_risk_level(review_text: str) -> str:
    match = re.search(
        r"(?:风险等级|Risk level)[:：]?\s*(low|medium|high|高风险|中风险|低风险|高|中|低)",
        review_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return "medium"
    level = match.group(1).lower()
    risk_level_map = {
        "high": "high",
        "高风险": "high",
        "高": "high",
        "medium": "medium",
        "中风险": "medium",
        "中": "medium",
        "low": "low",
        "低风险": "low",
        "低": "low",
    }
    return risk_level_map.get(level, "medium")


def _parse_total_score(review_text: str) -> int:
    match = re.search(r"总分[:：]\s*(\d+)分?", review_text)
    return int(match.group(1)) if match else 0


def parse_baseline_review(review_text: str) -> dict:
    sections = _split_sections(review_text or "")
    return {
        "confirmed_issues": _parse_bullet_lines(sections.get("已确认问题", "")),
        "potential_risks": _parse_bullet_lines(sections.get("待关注风险", "")),
        "investigation_summary": _parse_bullet_lines(sections.get("调查摘要", "")),
        "evidence_summary": _parse_bullet_lines(sections.get("证据与判断依据", "")),
        "score_detail": _parse_bullet_lines(sections.get("评分明细", "")),
        "recommendations": _parse_bullet_lines(sections.get("建议", "")),
        "risk_level": _parse_risk_level(review_text or ""),
        "total_score": _parse_total_score(review_text or ""),
    }
