from dataclasses import dataclass

from config.settings import settings
from storage.postgres.repository import record_prompt


@dataclass(frozen=True)
class Prompt:
    prompt_id: str
    version: str
    content: str


DEFAULT_PROMPTS = {
    "supervisor_v1": "Plan generic task execution. Do not make domain-specific legal judgments.",
    "worker_general_v1": "Understand, extract, summarize, retrieve context, and produce structured output.",
    "reviewer_v1": "Check completeness, missing information, source usage, output conflicts, and retry need.",
    "retrieval_query_v1": "Convert the user request into a retrieval query without adding domain conclusions.",
}


class PromptRegistry:
    def get(self, prompt_id: str) -> Prompt:
        content = DEFAULT_PROMPTS[prompt_id]
        version = "v1"
        try:
            record_prompt(prompt_id, version, content, settings.model_name)
        except Exception:
            pass
        return Prompt(prompt_id, version, content)
