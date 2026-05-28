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

PROJECT_DEEP_REVIEW_PROFILES = {
    "default_review": ReviewProfile(
        profile_name="default_review",
        mode="project_deep_review",
        dimension_definitions=(
            ReviewDimension(
                "stability",
                "功能稳定性",
                25,
                "关注近期多条 PR/MR 叠加后的功能稳定程度。",
            ),
            ReviewDimension(
                "risk_control",
                "风险控制能力",
                25,
                "关注风险是否被及时识别和收敛。",
            ),
            ReviewDimension(
                "testing",
                "测试与验证充分性",
                25,
                "关注跨 PR 的验证覆盖与回归防线。",
            ),
            ReviewDimension(
                "maintainability",
                "工程可维护性",
                25,
                "关注模块边界、重复问题和长期演进成本。",
            ),
        ),
        section_titles=(
            "项目总体结论",
            "阶段性高风险主题",
            "重复出现的问题模式",
            "热点模块与影响范围",
            "证据与判断依据",
            "评分明细",
            "改进建议",
            "风险等级",
            "总分",
        ),
        prompt_template_id="project_deep_review_prompt",
        total_score_formula="sum(dimensions)",
    ),
    "security_review": ReviewProfile(
        profile_name="security_review",
        mode="project_deep_review",
        dimension_definitions=(
            ReviewDimension(
                "stability",
                "功能稳定性",
                25,
                "关注近期多条 PR/MR 叠加后的功能稳定程度。",
            ),
            ReviewDimension(
                "security",
                "安全与数据风险控制",
                25,
                "关注鉴权、越权、敏感数据和数据一致性。",
            ),
            ReviewDimension(
                "testing",
                "测试与验证充分性",
                25,
                "关注安全路径、异常路径和回归验证。",
            ),
            ReviewDimension(
                "governance",
                "架构治理情况",
                25,
                "关注模块边界、配置治理和长期技术债。",
            ),
        ),
        section_titles=(
            "项目总体结论",
            "阶段性高风险主题",
            "重复出现的问题模式",
            "热点模块与影响范围",
            "证据与判断依据",
            "评分明细",
            "改进建议",
            "风险等级",
            "总分",
        ),
        prompt_template_id="project_deep_review_prompt",
        total_score_formula="sum(dimensions)",
    ),
}


def resolve_review_profile(mode: str, repo_full_name: str | None) -> ReviewProfile:
    default_name = os.getenv("AGENT_REVIEW_PROFILE", "default_review")
    repo_mapping = os.getenv("AGENT_REVIEW_PROFILE_REPOS", "")
    selected_name = _resolve_repo_mapping(repo_mapping, repo_full_name) or default_name
    profiles = _get_profiles_by_mode(mode)
    return profiles.get(selected_name, profiles["default_review"])


def get_review_profile(mode: str, profile_name: str) -> ReviewProfile:
    profiles = _get_profiles_by_mode(mode)
    return profiles.get(profile_name, profiles["default_review"])


def _get_profiles_by_mode(mode: str) -> dict[str, ReviewProfile]:
    if mode == "baseline_review":
        return BASELINE_PROFILES
    if mode == "project_deep_review":
        return PROJECT_DEEP_REVIEW_PROFILES
    raise ValueError(f"Unsupported review mode: {mode}")


def _resolve_repo_mapping(raw_mapping: str, repo_full_name: str | None) -> str | None:
    if not raw_mapping or not repo_full_name:
        return None
    for pair in raw_mapping.split(","):
        repo_name, _, profile_name = pair.partition(":")
        if repo_name.strip() == repo_full_name.strip():
            return profile_name.strip()
    return None
