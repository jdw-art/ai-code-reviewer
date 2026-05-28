#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from unittest import TestCase, main

from biz.platforms.gitlab.webhook_handler import PushHandler


# GitLab PushHandler 基础行为测试。
class TestPushHandler(TestCase):
    def setUp(self):
        """设置测试环境"""
        self.sample_webhook_data = {
            'event_name': 'push',
            'project': {
                'id': 0
            },
            'commits': [
                {
                    'message': 'Update service',
                    'author': {'name': 'Tester'},
                    'timestamp': '2025-03-18T17:58:00Z',
                    'url': 'https://gitlab.example.com/owner/repo/-/commit/commit123',
                }
            ],
        }
        self.gitlab_token = ''
        self.gitlab_url = ''

        # 创建 PushHandler 实例。
        self.handler = PushHandler(self.sample_webhook_data, self.gitlab_token, self.gitlab_url)

    def test_get_push_commits(self):
        """测试从 push webhook 中提取提交信息"""
        commits = self.handler.get_push_commits()

        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]['message'], 'Update service')
        self.assertEqual(commits[0]['author'], 'Tester')


if __name__ == '__main__':
    main()
