from unittest import TestCase, main

from biz.agent.deep_review.task import (
    ProjectDeepReviewRunTrace,
    ProjectDeepReviewSessionSnapshot,
)


class TestProjectDeepReviewTaskTypes(TestCase):
    def test_session_snapshot_defaults_to_plain_collections(self):
        snapshot = ProjectDeepReviewSessionSnapshot(
            session_id=12,
            platform="github",
            project_id="owner/repo",
            project_name="repo",
            profile_name="default_review",
        )

        self.assertEqual(snapshot.review_log_ids, [])
        self.assertEqual(snapshot.baseline_snapshot, {})
        self.assertEqual(snapshot.session_summary, {})

    def test_run_trace_keeps_round_and_tool_outputs(self):
        trace = ProjectDeepReviewRunTrace(
            session_id=12,
            user_message_id=34,
            profile_name="default_review",
            round_count=2,
            stop_reason="round_limit",
            rounds=[{"round": 1, "notes": ["聚焦鉴权问题"]}],
            tool_outputs=[{"tool": "group_reviews_by_module", "payload": [{"module": "backend", "count": 2}]}],
        )

        self.assertEqual(trace.round_count, 2)
        self.assertEqual(trace.stop_reason, "round_limit")
        self.assertEqual(trace.rounds[0]["round"], 1)
        self.assertEqual(trace.tool_outputs[0]["tool"], "group_reviews_by_module")


if __name__ == "__main__":
    main()
