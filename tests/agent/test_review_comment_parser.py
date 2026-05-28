from unittest import TestCase, main

from biz.agent.review_comment_parser import parse_baseline_review


class TestReviewCommentParser(TestCase):
    def test_parse_chinese_sections(self):
        review_text = """已确认问题
- 登录逻辑遗漏租户校验

待关注风险
- 测试未覆盖旧 token 兼容路径

调查摘要
- 检查了 backend/auth.py 与 tests/test_auth.py

评分明细
- 功能正确性：18/25

风险等级
high

总分: 72分
"""
        parsed = parse_baseline_review(review_text)

        self.assertEqual(parsed["confirmed_issues"], ["登录逻辑遗漏租户校验"])
        self.assertEqual(parsed["potential_risks"], ["测试未覆盖旧 token 兼容路径"])
        self.assertEqual(parsed["investigation_summary"], ["检查了 backend/auth.py 与 tests/test_auth.py"])
        self.assertEqual(parsed["risk_level"], "high")
        self.assertEqual(parsed["total_score"], 72)

    def test_parse_chinese_risk_level_words(self):
        review_text = """已确认问题
- 权限边界校验缺失

风险等级：高风险

总分: 61分
"""

        parsed = parse_baseline_review(review_text)

        self.assertEqual(parsed["risk_level"], "high")
        self.assertEqual(parsed["confirmed_issues"], ["权限边界校验缺失"])


if __name__ == "__main__":
    main()
