import abc
import os
import re
from typing import Dict, Any, List

import yaml
from jinja2 import Template

from biz.agent.review_profile import get_review_profile, resolve_review_profile
from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.token_util import count_tokens, truncate_text_by_tokens


class BaseReviewer(abc.ABC):
    """代码审查基类"""

    def __init__(
        self,
        prompt_key: str,
        review_profile: str | None = None,
        repo_full_name: str | None = None,
    ):
        self.client = Factory().getClient()
        resolved_profile = resolve_review_profile("baseline_review", repo_full_name)
        selected_profile_name = self._select_profile_name(review_profile, resolved_profile.profile_name)
        self.profile = get_review_profile("baseline_review", selected_profile_name)
        self.review_mode_name = self.profile.mode
        self.review_profile_name = self.profile.profile_name
        self.repo_full_name = repo_full_name
        self.prompts = self._load_prompts(prompt_key, os.getenv("REVIEW_STYLE", "professional"))

    @staticmethod
    def _select_profile_name(review_profile: str | None, resolved_profile_name: str) -> str:
        """选择最终生效的 profile 名称。"""
        if review_profile is not None:
            return review_profile
        return resolved_profile_name

    def _load_prompts(self, prompt_key: str, style="professional") -> Dict[str, Any]:
        """加载提示词配置"""
        prompt_templates_file = "conf/prompt_templates.yml"
        try:
            # 在打开 YAML 文件时显式指定编码为 UTF-8，避免使用系统默认的 GBK 编码。
            with open(prompt_templates_file, "r", encoding="utf-8") as file:
                prompts = yaml.safe_load(file).get(prompt_key, {})
                prompt_context = {"style": style, **self._profile_prompt_context()}

                # 使用 Jinja2 渲染模板
                def render_template(template_str: str) -> str:
                    return Template(template_str).render(**prompt_context)

                system_prompt = render_template(prompts["system_prompt"])
                user_prompt = render_template(prompts["user_prompt"])

                return {
                    "system_message": {"role": "system", "content": system_prompt},
                    "user_message": {"role": "user", "content": user_prompt},
                }
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            logger.error(f"加载提示词配置失败: {e}")
            raise Exception(f"提示词配置加载失败: {e}")

    def _profile_prompt_context(self) -> dict[str, str]:
        """构造 profile 相关的提示词上下文。"""
        dimension_lines = "\n".join(
            f"- {item.title}（{item.weight}分）：{item.guidance}" for item in self.profile.dimension_definitions
        )
        section_lines = "\n".join(f"{index + 1}. {title}" for index, title in enumerate(self.profile.section_titles))
        return {
            "profile_name": self.profile.profile_name,
            "dimension_lines": dimension_lines,
            "section_lines": section_lines,
            "total_score_formula": "总分 = 各维度得分直接求和，满分 100 分。",
        }

    def call_llm(self, messages: List[Dict[str, Any]]) -> str:
        """调用 LLM 进行代码审核"""
        total_tokens = sum(count_tokens(str(message.get("content", ""))) for message in messages)
        logger.info("向 AI 发送代码 Review 请求, message_count=%s, approx_tokens=%s", len(messages), total_tokens)
        review_result = self.client.completions(messages=messages)
        logger.info("收到 AI 返回结果, response_length=%s", len(review_result or ""))
        return review_result

    @abc.abstractmethod
    def review_code(self, *args, **kwargs) -> str:
        """抽象方法，子类必须实现"""
        pass


class CodeReviewer(BaseReviewer):
    """代码 Diff 级别的审查"""

    def __init__(self, review_profile: str | None = None, repo_full_name: str | None = None):
        super().__init__("baseline_review_prompt", review_profile=review_profile, repo_full_name=repo_full_name)

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        """
        Review判断changes_text超出取前REVIEW_MAX_TOKENS个token，超出则截断changes_text，
        调用review_code方法，返回review_result，如果review_result是markdown格式，则去掉头尾的```
        :param changes_text:
        :param commits_text:
        :return:
        """
        # 如果超长，取前REVIEW_MAX_TOKENS个token
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 10000))
        # 如果changes为空,打印日志
        if not changes_text:
            logger.info("代码为空, diffs_text = %", str(changes_text))
            return "代码为空"

        # 计算tokens数量，如果超过REVIEW_MAX_TOKENS，截断changes_text
        tokens_count = count_tokens(changes_text)
        if tokens_count > review_max_tokens:
            changes_text = truncate_text_by_tokens(changes_text, review_max_tokens)

        review_result = self.review_code(changes_text, commits_text).strip()
        if review_result.startswith("```markdown") and review_result.endswith("```"):
            return review_result[11:-3].strip()
        return review_result

    def review_code(self, diffs_text: str, commits_text: str = "") -> str:
        """Review 代码并返回结果"""
        messages = [
            self.prompts["system_message"],
            {
                "role": "user",
                "content": self.prompts["user_message"]["content"].format(
                    diffs_text=diffs_text, commits_text=commits_text
                ),
            },
        ]
        return self.call_llm(messages)

    @staticmethod
    def parse_review_score(review_text: str) -> int:
        """解析 AI 返回的 Review 结果，返回评分"""
        if not review_text:
            return 0
        match = re.search(r"总分[:：]\s*(\d+)分?", review_text)
        return int(match.group(1)) if match else 0

    @staticmethod
    def parse_risk_level(review_text: str) -> str:
        """解析风险等级，缺失时使用 medium 兜底。"""
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


class AgentCodeReviewer(BaseReviewer):
    """基于结构化证据的调查型审查器。"""

    # 输出契约单独保留，避免 evidence 被截断时把“总分”等关键要求一起截掉。
    OUTPUT_REQUIREMENTS = """请输出 Markdown，并严格使用以下中文标题：
1. 已确认问题
2. 待关注风险
3. 调查摘要
4. 证据与判断依据
5. 评分明细
6. 建议
7. 风险等级
8. 总分

评分要求：
- 必须给出每个维度的得分和扣分依据
- 风险等级只能填写 low、medium、high 之一
- 总分 = 各维度得分直接求和
- 总分格式必须为：总分: XX分
"""

    def __init__(self, review_profile: str | None = None, repo_full_name: str | None = None):
        super().__init__("agent_code_review_prompt", review_profile=review_profile, repo_full_name=repo_full_name)

    def _requirements_for_budget(self) -> str:
        """返回用于 token 预算估算的输出契约文本。"""
        # 兼容既有测试与预算逻辑，不影响真正发送给模型的中文输出契约。
        return f"{self.OUTPUT_REQUIREMENTS}\nScore in this exact parseable format: 总分: XX分"

    def review_evidence(self, evidence_text: str) -> str:
        """在 token 预算内发送 evidence，并确保输出契约始终保留。"""
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 10000))
        requirements_tokens = count_tokens(self._requirements_for_budget())
        evidence_max_tokens = max(review_max_tokens - requirements_tokens, 1)
        tokens_count = count_tokens(evidence_text)
        if tokens_count > evidence_max_tokens:
            evidence_text = truncate_text_by_tokens(evidence_text, evidence_max_tokens)

        review_result = self.review_code(evidence_text, self.OUTPUT_REQUIREMENTS).strip()
        if review_result.startswith("```markdown") and review_result.endswith("```"):
            return review_result[11:-3].strip()
        return review_result

    def review_code(self, evidence_text: str, output_requirements: str | None = None) -> str:
        """组装最终消息；输出要求放在 evidence 外层以提高抗注入优先级。"""
        messages = [
            self.prompts["system_message"],
            {
                "role": "user",
                "content": self.prompts["user_message"]["content"].format(
                    evidence_text=evidence_text,
                    output_requirements=output_requirements or self.OUTPUT_REQUIREMENTS,
                ),
            },
        ]
        return self.call_llm(messages)
