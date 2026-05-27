#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from unittest import TestCase, main

from biz.platforms.github.webhook_handler import PushHandler


# GitHub PushHandler 基础行为测试。
class TestPushHandler(TestCase):
    def setUp(self):
        """设置测试环境"""
        self.sample_webhook_data = {
            'repository': {
                'full_name': 'owner/repo'
            },
            'ref': 'refs/heads/main',
            'commits': [
                {
                    'id': 'sample_commit_id',
                    'message': 'Sample commit message',
                    'author': {
                        'name': 'Test Author'
                    },
                    'timestamp': '2023-01-01T12:00:00Z',
                    'url': 'https://github.com/owner/repo/commit/sample_commit_id'
                }
            ]
        }
        self.github_token = ''
        self.github_url = 'https://github.com'

        # 创建 PushHandler 实例。
        self.handler = PushHandler(self.sample_webhook_data, self.github_token, self.github_url)

    def test_get_parent_commit_id(self):
        """测试获取父提交ID"""
        commit_id = 'sample_commit_id'
        # 调用测试方法。
        parent_id = self.handler.get_parent_commit_id(commit_id)

        # 当前测试只约束返回类型，避免依赖真实 GitHub 仓库状态。
        self.assertIsInstance(parent_id, str)


if __name__ == '__main__':
    main()
