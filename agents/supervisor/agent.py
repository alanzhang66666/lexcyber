from dataclasses import dataclass


@dataclass
class Plan:
    steps: list[str]
    needs_retrieval: bool = True


class SupervisorAgent:
    def plan(self, user_query: str) -> Plan:
        return Plan(steps=["worker", "tool", "reviewer"], needs_retrieval=bool(user_query.strip()))
