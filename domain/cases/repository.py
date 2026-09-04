from typing import Any

from domain.cases.models import Matter
from storage.postgres.domain_store import create_case, get_case


def create_matter(title: str, jurisdiction: str | None = "CN", as_of_date: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    matter = Matter(title=title, jurisdiction=jurisdiction, as_of_date=as_of_date, metadata=metadata or {})
    return create_case(matter.title, matter.jurisdiction, matter.as_of_date, matter.metadata)


def load_matter(case_id: str) -> dict[str, Any] | None:
    return get_case(case_id)
