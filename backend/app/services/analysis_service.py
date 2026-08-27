from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.schemas.analysis import AnalysisFinding, AnalysisMetrics, RepositoryAnalysisResponse
from app.schemas.github import CommitSummary, IssueSummary, PullRequestSummary, RepositoryContent, RepositorySummary
from app.services.github_service import GitHubService


class RepositoryAnalysisService:
    def __init__(self, github_service: GitHubService) -> None:
        self.github_service = github_service

    async def analyze(self, owner: str, repo: str) -> RepositoryAnalysisResponse:
        repository, commits, issues, pull_requests, contents = await asyncio.gather(
            self.github_service.get_repository_async(owner, repo),
            self.github_service.get_commits_async(owner, repo, per_page=30),
            self.github_service.get_issues_async(owner, repo, state="open", per_page=30),
            self.github_service.get_pull_requests_async(owner, repo, state="open", per_page=30),
            self.github_service.get_contents_async(owner, repo, per_page=50),
        )
        root_contents = contents if isinstance(contents, list) else [contents]
        metrics = self._metrics(repository, commits, issues, pull_requests, root_contents)
        findings = self._findings(metrics)
        summary = self._summary(metrics, findings)
        return RepositoryAnalysisResponse(
            owner=owner,
            repository=repo,
            analyzed_at=datetime.now(timezone.utc),
            summary=summary,
            metrics=metrics,
            findings=findings,
        )

    @staticmethod
    def _metrics(
        repository: RepositorySummary,
        commits: list[CommitSummary],
        issues: list[IssueSummary],
        pull_requests: list[PullRequestSummary],
        contents: list[RepositoryContent],
    ) -> AnalysisMetrics:
        names = {item.name.lower() for item in contents}
        return AnalysisMetrics(
            commit_count=len(commits),
            open_issue_count=len(issues),
            open_pull_request_count=len(pull_requests),
            root_content_count=len(contents),
            has_readme="readme.md" in names or "readme" in names,
            has_ci_configuration=any(
                name.startswith(".github") or name in {"jenkinsfile", ".travis.yml", "circle.yml"}
                for name in names
            ),
        )

    @staticmethod
    def _findings(metrics: AnalysisMetrics) -> list[AnalysisFinding]:
        findings: list[AnalysisFinding] = []
        if metrics.commit_count == 0:
            findings.append(AnalysisFinding(
                title="No recent commits found",
                description="The analyzed GitHub commit page contains no commits.",
                severity="HIGH",
                category="activity",
                evidence="commit_count=0",
            ))
        elif metrics.commit_count < 3:
            findings.append(AnalysisFinding(
                title="Low recent commit activity",
                description="Fewer than three commits were returned from the recent commit page.",
                severity="LOW",
                category="activity",
                evidence=f"commit_count={metrics.commit_count}",
            ))

        if metrics.open_issue_count > 20:
            findings.append(AnalysisFinding(
                title="Large open issue backlog",
                description="The repository reports more than twenty open issues.",
                severity="MEDIUM",
                category="maintenance",
                evidence=f"open_issue_count={metrics.open_issue_count}",
            ))
        if metrics.open_pull_request_count > 10:
            findings.append(AnalysisFinding(
                title="Large open pull request queue",
                description="More than ten open pull requests were returned.",
                severity="MEDIUM",
                category="maintenance",
                evidence=f"open_pull_request_count={metrics.open_pull_request_count}",
            ))
        if not metrics.has_readme:
            findings.append(AnalysisFinding(
                title="README not found at repository root",
                description="A README file was not present in the analyzed root contents.",
                severity="LOW",
                category="maintenance",
                evidence="has_readme=false",
            ))
        if not metrics.has_ci_configuration:
            findings.append(AnalysisFinding(
                title="CI configuration not detected",
                description="No common CI configuration was present in the analyzed root contents.",
                severity="INFO",
                category="automation",
                evidence="has_ci_configuration=false",
            ))
        if not findings:
            findings.append(AnalysisFinding(
                title="No deterministic concerns detected",
                description="The analyzed repository data did not trigger any V1 warning rules.",
                severity="INFO",
                category="health",
                evidence="all_v1_rules_passed",
            ))
        return findings

    @staticmethod
    def _summary(metrics: AnalysisMetrics, findings: list[AnalysisFinding]) -> str:
        highest = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1}
        severity = max(findings, key=lambda finding: highest[finding.severity]).severity
        return f"Repository analysis completed with highest finding severity: {severity}."