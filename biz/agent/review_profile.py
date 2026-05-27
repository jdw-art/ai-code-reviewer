import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewDimension:
    key: str
    title: str
    weight: int
    guidance: str


@dataclass(frozen=True)
class ReviewProfile:
    profile_name: str
    mode: str
    dimension_definitions: tuple[ReviewDimension, ...]
    section_titles: tuple[str, ...]
    prompt_template_id: str
    total_score_formula: str


BASELINE_PROFILES = {
    "default_review": ReviewProfile(
        profile_name="default_review",
        mode="baseline_review",
        dimension_definitions=(
            ReviewDimension(
                "correctness",
                "功能正确性",
                25,
                "重点检查功能语义、边界条件和兼容性。",
            ),
            ReviewDimension(
                "risk_control",
                "风险控制",
                25,
                "重点检查回滚风险、数据风险和变更面。",
            ),
            ReviewDimension(
                "testing",
                "测试充分性",
                25,
                "重点检查关键路径是否有对应测试。",
            ),
            ReviewDimension(
                "maintainability",
                "可维护性",
                25,
                "重点检查结构清晰度、命名和后续扩展成本。",
            ),
        ),
        section_titles=(
            "已确认问题",
            "待关注风险",
            "调查摘要",
            "证据与判断依据",
            "评分明细",
            "建议",
            "风险等级",
            "总分",
        ),
        prompt_template_id="baseline_review_prompt",
        total_score_formula="sum(dimensions)",
    ),
    "security_review": ReviewProfile(
        profile_name="security_review",
        mode="baseline_review",
        dimension_definitions=(
            ReviewDimension(
                "correctness",
                "功能正确性",
                25,
                "重点检查功能语义、边界条件和兼容性。",
            ),
            ReviewDimension(
                "security",
                "安全与数据风险",
                25,
                "重点检查鉴权、越权、注入、敏感数据与数据一致性。",
            ),
            ReviewDimension(
                "testing",
                "测试充分性",
                25,
                "重点检查安全与异常路径是否被验证。",
            ),
            ReviewDimension(
                "architecture",
                "架构与可维护性",
                25,
                "重点检查职责边界、配置治理和长期演进成本。",
            ),
        ),
        section_titles=(
            "已确认问题",
            "待关注风险",
            "调查摘要",
            "证据与判断依据",
            "评分明细",
            "建议",
            "风险等级",
            "总分",
        ),
        prompt_template_id="baseline_review_prompt",
        total_score_formula="sum(dimensions)",
    ),
}


def resolve_review_profile(mode: str, repo_full_name: str | None) -> ReviewProfile:
    default_name = os.getenv("AGENT_REVIEW_PROFILE", "default_review")
    repo_mapping = os.getenv("AGENT_REVIEW_PROFILE_REPOS", "")
    selected_name = _resolve_repo_mapping(repo_mapping, repo_full_name) or default_name
    if mode == "baseline_review":
        return BASELINE_PROFILES.get(selected_name, BASELINE_PROFILES["default_review"])
    raise ValueError(f"Unsupported review mode: {mode}")


def get_review_profile(mode: str, profile_name: str) -> ReviewProfile:
    if mode == "baseline_review":
        return BASELINE_PROFILES.get(profile_name, BASELINE_PROFILES["default_review"])
    raise ValueError(f"Unsupported review mode: {mode}")


def _resolve_repo_mapping(raw_mapping: str, repo_full_name: str | None) -> str | None:
    if not raw_mapping or not repo_full_name:
        return None
    for pair in raw_mapping.split(","):
        repo_name, _, profile_name = pair.partition(":")
        if repo_name.strip() == repo_full_name.strip():
            return profile_name.strip()
    return None
