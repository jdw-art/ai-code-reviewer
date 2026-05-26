import os
import re

from biz.agent.task import ChangedFile, DiffAnalysis


class DiffAnalyzer:
    LANGUAGE_BY_EXTENSION = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".go": "go",
        ".php": "php",
        ".vue": "vue",
        ".sql": "sql",
        ".yml": "yaml",
        ".yaml": "yaml",
    }

    SECURITY_KEYWORDS = ("auth", "token", "password", "permission", "security")
    BUSINESS_KEYWORDS = ("payment", "order", "refund")
    DATABASE_KEYWORDS = ("migration", "sql", "db", "database")
    INTERFACE_KEYWORDS = ("api", "router", "controller")

    def analyze(self, changes: list[dict]) -> DiffAnalysis:
        files = [self._analyze_change(change) for change in changes]
        risk_hints = sorted({tag for file in files for tag in file.risk_tags})
        return DiffAnalysis(
            files=files,
            total_additions=sum(file.additions for file in files),
            total_deletions=sum(file.deletions for file in files),
            risk_hints=risk_hints,
        )

    def _analyze_change(self, change: dict) -> ChangedFile:
        path = change.get("new_path") or change.get("old_path") or ""
        diff = change.get("diff", "")
        return ChangedFile(
            path=path,
            language=self._detect_language(path),
            additions=int(change.get("additions", 0) or 0),
            deletions=int(change.get("deletions", 0) or 0),
            is_test=self._is_test_path(path),
            is_config=self._is_config_path(path),
            risk_tags=self._risk_tags(path),
            changed_symbols=self._changed_symbols(diff),
        )

    def _detect_language(self, path: str) -> str:
        _, ext = os.path.splitext(path.lower())
        return self.LANGUAGE_BY_EXTENSION.get(ext, "unknown")

    def _is_test_path(self, path: str) -> bool:
        normalized = path.lower().replace("\\", "/")
        basename = os.path.basename(normalized)
        return (
            "/test/" in normalized
            or "/tests/" in normalized
            or normalized.startswith("test/")
            or normalized.startswith("tests/")
            or "spec" in basename
            or basename.startswith("test_")
            or "_test" in basename
        )

    def _is_config_path(self, path: str) -> bool:
        normalized = path.lower()
        basename = os.path.basename(normalized)
        return (
            "config" in normalized
            or basename.startswith(".env")
            or basename in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
            or normalized.endswith((".yml", ".yaml"))
        )

    def _risk_tags(self, path: str) -> list[str]:
        normalized = path.lower()
        tags = set()
        if any(keyword in normalized for keyword in self.SECURITY_KEYWORDS):
            tags.add("security")
        if any(keyword in normalized for keyword in self.BUSINESS_KEYWORDS):
            tags.add("business_critical")
        if any(keyword in normalized for keyword in self.DATABASE_KEYWORDS):
            tags.add("database")
        if any(keyword in normalized for keyword in self.INTERFACE_KEYWORDS):
            tags.add("interface")
        if self._is_config_path(path):
            tags.add("config")
        return sorted(tags)

    def _changed_symbols(self, diff: str) -> list[str]:
        patterns = [
            r"^\+\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            r"^\+\s*class\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"^\+\s*function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
            r"^\+\s*export\s+(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
            r"^\+\s*export\s+class\s+([A-Za-z_$][A-Za-z0-9_$]*)",
            r"^\+\s*func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        ]
        symbols = []
        for pattern in patterns:
            symbols.extend(re.findall(pattern, diff, flags=re.MULTILINE))
        return sorted(set(symbols))
