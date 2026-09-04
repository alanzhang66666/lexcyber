from typing import Any, Literal

from pydantic import BaseModel, Field

ReviewStatus = Literal["PASS", "RETRY", "NEED_HUMAN"]


class ReviewResult(BaseModel):
    status: ReviewStatus
    issues: list[dict[str, Any]] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    invalid_citations: list[str] = Field(default_factory=list)
    retry_instructions: str | None = None


class ReviewerAgent:
    def review(self, user_query: str, final_candidate: str, retry_count: int, state: dict[str, Any] | None = None) -> ReviewStatus:
        return self.review_detailed(user_query, final_candidate, retry_count, state).status

    def review_detailed(self, user_query: str, final_candidate: str, retry_count: int, state: dict[str, Any] | None = None) -> ReviewResult:
        state = state or {}
        issues: list[dict[str, Any]] = []
        missing: list[str] = []
        unsupported: list[str] = []
        invalid: list[str] = []
        if not str(final_candidate or "").strip():
            return ReviewResult(status="RETRY" if retry_count < 2 else "NEED_HUMAN", issues=[{"type": "empty_output"}], retry_instructions="produce a non-empty structured result")
        if not str(user_query or "").strip():
            return ReviewResult(status="NEED_HUMAN", issues=[{"type": "empty_query"}])
        if state.get("human_approval_required"):
            return ReviewResult(status="NEED_HUMAN", issues=[{"type": "human_gate"}])
        for result in state.get("skill_results", []):
            output = result.get("output") or {}
            missing.extend(output.get("missing") or [])
            unsupported.extend(output.get("unsupported_claims") or [])
            if result.get("status") in {"failed", "timeout"}:
                issues.append({"type": "skill_error", "skill_id": result.get("skill_id"), "error": result.get("error")})
            if result.get("status") == "need_human":
                return ReviewResult(status="NEED_HUMAN", issues=[{"type": "skill_need_human", "skill_id": result.get("skill_id")}])
            if result.get("status") == "denied":
                issues.append({"type": "skill_denied", "skill_id": result.get("skill_id")})
            if output.get("status") == "unavailable":
                invalid.append(str(output.get("citation") or result.get("skill_id")))
            if output.get("need_human"):
                return ReviewResult(status="NEED_HUMAN", issues=[{"type": "human_gate", "reasons": output.get("reasons", [])}], missing_information=missing)
            if output.get("has_conflict") or output.get("status") == "FAIL":
                issues.append({"type": "conflict", "skill_id": result.get("skill_id")})
        if issues and retry_count < 2:
            return ReviewResult(status="RETRY", issues=issues, missing_information=missing, unsupported_claims=unsupported, invalid_citations=invalid, retry_instructions="repair skill errors or conflicts")
        if issues or invalid:
            return ReviewResult(status="NEED_HUMAN", issues=issues, missing_information=missing, unsupported_claims=unsupported, invalid_citations=invalid)
        return ReviewResult(status="PASS", missing_information=missing, unsupported_claims=unsupported, invalid_citations=invalid)
