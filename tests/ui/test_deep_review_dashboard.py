from unittest import TestCase, main

from biz.ui.deep_review_dashboard import (
    build_project_options,
    build_project_source_options,
    build_message_timeline,
    build_session_options,
    filter_rows_by_project,
    format_session_label,
    summarize_run_result,
)


class TestDeepReviewDashboardHelpers(TestCase):
    def test_build_project_options_deduplicates_and_sorts(self):
        rows = [
            {"project_id": "owner/repo-b", "project_name": "repo-b"},
            {"project_id": "owner/repo-a", "project_name": "repo-a"},
            {"project_id": "owner/repo-a", "project_name": "repo-a"},
        ]

        options = build_project_options(rows)

        self.assertEqual(
            options,
            [
                ("owner/repo-a", "repo-a（owner/repo-a）"),
                ("owner/repo-b", "repo-b（owner/repo-b）"),
            ],
        )

    def test_format_session_label_contains_range_and_profile(self):
        session = {
            "id": 7,
            "project_name": "repo",
            "profile_name": "security_review",
            "time_range_start": 1716806400,
            "time_range_end": 1717411199,
        }

        label = format_session_label(session)

        self.assertIn("repo", label)
        self.assertIn("security_review", label)
        self.assertIn("#7", label)
        self.assertIn("2024-05-27 ~ 2024-06-03", label)

    def test_summarize_run_result_reads_total_score_line(self):
        text = "项目总体结论\n- 鉴权与测试回归反复出现\n\n总分: 68分"

        summary = summarize_run_result(text)

        self.assertIn("68分", summary)

    def test_project_option_label_keeps_repo_id(self):
        options = build_project_options([{"project_id": "owner/repo", "project_name": "repo"}])

        self.assertEqual(options[0][1], "repo（owner/repo）")

    def test_filter_rows_by_project_keeps_matching_rows(self):
        rows = [
            {"id": 1, "project_id": "owner/repo-a"},
            {"id": 2, "project_id": "owner/repo-b"},
            {"id": 3, "project_id": "owner/repo-a"},
        ]

        filtered = filter_rows_by_project(rows, "owner/repo-a")

        self.assertEqual([row["id"] for row in filtered], [1, 3])

    def test_build_session_options_uses_session_label(self):
        sessions = [
            {
                "id": 8,
                "project_name": "repo",
                "profile_name": "default_review",
                "time_range_start": 1716806400,
                "time_range_end": 1717411199,
            }
        ]

        options = build_session_options(sessions)

        self.assertEqual(options[0][0], 8)
        self.assertIn("default_review", options[0][1])

    def test_build_message_timeline_keeps_role_and_content(self):
        timeline = build_message_timeline(
            [
                {"role": "user", "content": "最近有什么问题？", "created_at": 1},
                {"role": "assistant", "content": "项目总体结论", "created_at": 2},
            ]
        )

        self.assertEqual(
            timeline,
            [
                {"role": "user", "content": "最近有什么问题？"},
                {"role": "assistant", "content": "项目总体结论"},
            ],
        )

    def test_summarize_run_result_handles_empty_text(self):
        self.assertEqual(summarize_run_result(""), "暂无结论 | 总分未解析")

    def test_build_project_source_options_keeps_session_projects_when_no_baseline_rows(self):
        options = build_project_source_options(
            review_rows=[],
            sessions=[
                {
                    "id": 9,
                    "project_id": "owner/repo-session",
                    "project_name": "repo-session",
                }
            ],
        )

        self.assertEqual(options, [("owner/repo-session", "repo-session（owner/repo-session）")])

    def test_format_session_label_prefers_saved_display_dates(self):
        session = {
            "id": 11,
            "project_name": "repo",
            "profile_name": "default_review",
            "time_range_start": 1716806400,
            "time_range_end": 1717411199,
            "session_summary": {
                "display_time_range": {
                    "start_date": "2026-05-21",
                    "end_date": "2026-05-28",
                }
            },
        }

        label = format_session_label(session)

        self.assertIn("2026-05-21 ~ 2026-05-28", label)


if __name__ == "__main__":
    main()
