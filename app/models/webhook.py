"""The small portion of a GitHub issue event we need."""

from pydantic import AwareDatetime, BaseModel, Field


class GitHubIssue(BaseModel):
    number: int = Field(gt=0, strict=True)
    body: str | None = None
    updated_at: AwareDatetime | None = None
    # GitHub also sends issues events for pull requests. Exclude these.
    pull_request: dict | None = None


class GitHubLabel(BaseModel):
    name: str


class GitHubIssueEvent(BaseModel):
    action: str
    issue: GitHubIssue
    label: GitHubLabel | None = None
