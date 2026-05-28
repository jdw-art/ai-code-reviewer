import os
from unittest import TestCase
from unittest.mock import patch

from biz.utils.code_reviewer import AgentCodeReviewer, CodeReviewer


class TestCodeReviewerProfiles(TestCase):
    @patch("biz.utils.code_reviewer.Factory")
    def test_agent_prompt_contains_default_profile_sections(self, factory_cls):
        factory_cls.return_value.getClient.return_value.completions.return_value = "已确认问题\n总分: 88分"

        reviewer = AgentCodeReviewer(review_profile="default_review")
        reviewer.review_evidence("fake evidence")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("评分明细", system_prompt)
        self.assertIn("功能正确性", system_prompt)
        self.assertIn("可维护性", system_prompt)
        self.assertIn("low、medium、high", system_prompt)
        self.assertIn("已确认问题", user_prompt)

    @patch("biz.utils.code_reviewer.Factory")
    def test_classic_prompt_contains_security_dimensions(self, factory_cls):
        factory_cls.return_value.getClient.return_value.completions.return_value = "已确认问题\n总分: 80分"

        reviewer = CodeReviewer(review_profile="security_review")
        reviewer.review_and_strip_code("diff text", "commit text")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        system_prompt = messages[0]["content"]
        self.assertIn("安全与数据风险", system_prompt)
        self.assertIn("架构与可维护性", system_prompt)

    @patch("biz.utils.code_reviewer.Factory")
    def test_repo_mapping_selects_security_profile_when_only_repo_name_is_given(self, factory_cls):
        factory_cls.return_value.getClient.return_value.completions.return_value = "已确认问题\n总分: 80分"

        with patch.dict(os.environ, {"AGENT_REVIEW_PROFILE_REPOS": "org/security-service:security_review"}, clear=False):
            reviewer = CodeReviewer(repo_full_name="org/security-service")
            reviewer.review_and_strip_code("diff text", "commit text")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        system_prompt = messages[0]["content"]
        self.assertEqual(reviewer.profile.profile_name, "security_review")
        self.assertIn("安全与数据风险", system_prompt)
        self.assertIn("架构与可维护性", system_prompt)

    @patch("biz.utils.code_reviewer.Factory")
    def test_explicit_default_review_overrides_repo_mapping(self, factory_cls):
        factory_cls.return_value.getClient.return_value.completions.return_value = "已确认问题\n总分: 80分"

        with patch.dict(os.environ, {"AGENT_REVIEW_PROFILE_REPOS": "org/security-service:security_review"}, clear=False):
            reviewer = CodeReviewer(review_profile="default_review", repo_full_name="org/security-service")
            reviewer.review_and_strip_code("diff text", "commit text")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        system_prompt = messages[0]["content"]
        self.assertEqual(reviewer.profile.profile_name, "default_review")
        self.assertIn("风险控制", system_prompt)
        self.assertIn("可维护性", system_prompt)
        self.assertNotIn("安全与数据风险", system_prompt)
