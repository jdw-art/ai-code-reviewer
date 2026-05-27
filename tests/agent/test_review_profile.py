import os
from unittest import TestCase, main

from biz.agent.review_profile import resolve_review_profile


class TestReviewProfile(TestCase):
    def setUp(self):
        self.old_default = os.environ.get("AGENT_REVIEW_PROFILE")
        self.old_repo_map = os.environ.get("AGENT_REVIEW_PROFILE_REPOS")

    def tearDown(self):
        if self.old_default is None:
            os.environ.pop("AGENT_REVIEW_PROFILE", None)
        else:
            os.environ["AGENT_REVIEW_PROFILE"] = self.old_default

        if self.old_repo_map is None:
            os.environ.pop("AGENT_REVIEW_PROFILE_REPOS", None)
        else:
            os.environ["AGENT_REVIEW_PROFILE_REPOS"] = self.old_repo_map

    def test_repo_mapping_overrides_global_default(self):
        os.environ["AGENT_REVIEW_PROFILE"] = "default_review"
        os.environ["AGENT_REVIEW_PROFILE_REPOS"] = "org/security-service:security_review"

        profile = resolve_review_profile("baseline_review", "org/security-service")

        self.assertEqual(profile.profile_name, "security_review")
        self.assertEqual(
            [item.title for item in profile.dimension_definitions],
            [
                "功能正确性",
                "安全与数据风险",
                "测试充分性",
                "架构与可维护性",
            ],
        )

    def test_unknown_profile_falls_back_to_default_review(self):
        os.environ["AGENT_REVIEW_PROFILE"] = "unknown_profile"

        profile = resolve_review_profile("baseline_review", "owner/repo")

        self.assertEqual(profile.profile_name, "default_review")
        self.assertEqual(profile.total_score_formula, "sum(dimensions)")


if __name__ == "__main__":
    main()
