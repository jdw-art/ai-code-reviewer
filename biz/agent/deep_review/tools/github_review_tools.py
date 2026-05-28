import os

import requests

from biz.agent.tools.file_reader import GitHubFileReader


class GitHubDeepReviewTools:
    """项目级 Deep Review 使用的 GitHub 只读调查工具。"""

    def __init__(
        self,
        repo_full_name: str,
        token: str,
        api_base_url: str = "https://api.github.com",
        max_file_chars: int = 30000,
        timeout: int = 10,
    ):
        self.repo_full_name = repo_full_name
        self.token = token
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout
        self.file_reader = GitHubFileReader(
            repo_full_name=repo_full_name,
            token=token,
            api_base_url=api_base_url,
            max_file_chars=max_file_chars,
            timeout=timeout,
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def read_pr_metadata(self, pr_number: int) -> dict:
        """读取 PR 元信息；失败时返回空字典。"""
        url = f"{self.api_base_url}/repos/{self.repo_full_name}/pulls/{pr_number}"
        try:
            response = requests.get(url, headers=self._headers, timeout=self.timeout)
            if response.status_code != 200:
                return {}
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def read_pr_diff(self, pr_number: int) -> list[dict]:
        """读取 PR 文件 diff 列表；按页拉取，避免大 PR 被静默截断。"""
        url = f"{self.api_base_url}/repos/{self.repo_full_name}/pulls/{pr_number}/files"
        page = 1
        per_page = 100
        files: list[dict] = []
        try:
            while True:
                response = requests.get(
                    url,
                    headers=self._headers,
                    params={"page": page, "per_page": per_page},
                    timeout=self.timeout,
                )
                if response.status_code != 200:
                    return files
                payload = response.json()
                if not isinstance(payload, list):
                    return files
                files.extend(item for item in payload if isinstance(item, dict))
                if len(payload) < per_page:
                    return files
                page += 1
        except Exception:
            return files

    def read_repo_file(self, path: str, ref: str) -> dict:
        """读取仓库文件，并转换为便于后续工具消费的字典。"""
        result = self.file_reader.read_file(path, ref)
        if not result.ok:
            raise RuntimeError(result.error or f"GitHub file read failed: {path}@{ref}")
        return {
            "path": result.path,
            "ref": result.ref,
            "content": result.content,
            "truncated": result.truncated,
        }

    def read_related_test(self, path: str, ref: str) -> list[dict]:
        """返回实际可读到内容的候选测试文件。"""
        results: list[dict] = []
        for candidate in self._test_candidates(path):
            try:
                results.append(self.read_repo_file(candidate, ref))
            except Exception:
                continue
        return results

    def read_local_import(self, path: str, ref: str) -> list[dict[str, str]]:
        """提取相对导入语句，供后续 Agent 决定是否继续深入。"""
        source = self.read_repo_file(path, ref)["content"]
        imports: list[dict[str, str]] = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from .") or stripped.startswith("import ."):
                imports.append({"line": stripped})
        return imports

    def _test_candidates(self, path: str) -> list[str]:
        normalized = (path or "").strip().lstrip("/")
        directory = os.path.dirname(normalized)
        trimmed_directory = directory.split("/", 1)[1] if "/" in directory else ""
        filename = os.path.basename(normalized)
        stem, ext = os.path.splitext(filename)
        candidates = [
            f"tests/test_{stem}{ext}",
            f"tests/{stem}_test{ext}",
        ]
        for candidate_directory in (directory, trimmed_directory):
            if not candidate_directory:
                continue
            candidates.extend(
                [
                    f"tests/{candidate_directory}/test_{stem}{ext}",
                    f"tests/{candidate_directory}/{stem}_test{ext}",
                ]
            )
        deduplicated: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            deduplicated.append(candidate)
        return deduplicated
