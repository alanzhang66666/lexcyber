from typing import Literal


ReviewStatus = Literal["PASS", "RETRY", "NEED_HUMAN"]


class ReviewerAgent:
    def review(self, user_query: str, final_candidate: str, retry_count: int) -> ReviewStatus:
        if not final_candidate.strip():
            return "RETRY" if retry_count < 2 else "NEED_HUMAN"
        if not user_query.strip():
            return "NEED_HUMAN"
        return "PASS"
