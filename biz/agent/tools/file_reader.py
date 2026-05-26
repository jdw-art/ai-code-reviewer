import base64
from abc import ABC, abstractmethod
from urllib.parse import quote

import requests

from biz.agent.task import FileReadResult


class PlatformFileReader(ABC):
    @abstractmethod
    def read_file(self, path: str, ref: str) -> FileReadResult:
        raise NotImplementedError

    def file_exists(self, path: str, ref: str) -> bool:
        return self.read_file(path, ref).ok


class GitHubFileReader(PlatformFileReader):
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
        self.max_file_chars = max_file_chars
        self.timeout = timeout

    def read_file(self, path: str, ref: str) -> FileReadResult:
        encoded_path = quote(path, safe="/")
        url = f"{self.api_base_url}/repos/{self.repo_full_name}/contents/{encoded_path}"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            response = requests.get(url, headers=headers, params={"ref": ref}, timeout=self.timeout)
            if response.status_code != 200:
                return FileReadResult(
                    path=path,
                    ref=ref,
                    ok=False,
                    error=f"GitHub file read failed: {response.status_code} {response.text}",
                )
            payload = response.json()
            if isinstance(payload, list):
                return FileReadResult(path=path, ref=ref, ok=False, error="GitHub path is a directory")
            content = payload.get("content", "")
            encoding = payload.get("encoding", "")
            if encoding == "none" and not content:
                return FileReadResult(
                    path=path,
                    ref=ref,
                    ok=False,
                    truncated=True,
                    error="GitHub file content is unavailable via Contents API",
                )
            if encoding == "base64":
                decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            else:
                decoded = str(content)
            truncated = len(decoded) > self.max_file_chars
            if truncated:
                decoded = decoded[: self.max_file_chars]
            return FileReadResult(path=path, ref=ref, content=decoded, ok=True, truncated=truncated)
        except Exception as exc:
            return FileReadResult(path=path, ref=ref, ok=False, error=f"GitHub file read exception: {exc}")
