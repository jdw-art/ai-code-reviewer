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
        payload = str(messages)
        self.assertIn("已确认问题", payload)
        self.assertIn("评分明细", payload)
        self.assertIn("功能正确性", payload)
        self.assertIn("可维护性", payload)
        self.assertIn("low、medium、high", payload)

    @patch("biz.utils.code_reviewer.Factory")
    def test_classic_prompt_contains_security_dimensions(self, factory_cls):
        factory_cls.return_value.getClient.return_value.completions.return_value = "已确认问题\n总分: 80分"

        reviewer = CodeReviewer(review_profile="security_review")
        reviewer.review_and_strip_code("diff text", "commit text")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        payload = str(messages)
        self.assertIn("安全与数据风险", payload)
        self.assertIn("架构与可维护性", payload)

    @patch("biz.utils.code_reviewer.Factory")
    def test_repo_mapping_selects_security_profile_when_only_repo_name_is_given(self, factory_cls):
        factory_cls.return_value.getClient.return_value.completions.return_value = "已确认问题\n总分: 80分"

        with patch.dict(os.environ, {"AGENT_REVIEW_PROFILE_REPOS": "org/security-service:security_review"}, clear=False):
            reviewer = CodeReviewer(repo_full_name="org/security-service")
            reviewer.review_and_strip_code("diff text", "commit text")

        messages = factory_cls.return_value.getClient.return_value.completions.call_args.kwargs["messages"]
        payload = str(messages)
        self.assertEqual(reviewer.profile.profile_name, "security_review")
        self.assertIn("安全与数据风险", payload)
        self.assertIn("架构与可维护性", payload)
