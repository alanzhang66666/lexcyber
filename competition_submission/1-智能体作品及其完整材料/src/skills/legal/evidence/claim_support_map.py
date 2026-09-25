from typing import Any


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in value.replace("，", " ").replace("。", " ").split() if len(token) >= 2}


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    claims = payload.get("claims") or []
    evidence = payload.get("evidence") or payload.get("items") or []
    mappings = []
    for claim in claims:
        claim_text = claim if isinstance(claim, str) else str(claim.get("text") or claim.get("claim") or "")
        claim_tokens = _tokens(claim_text)
        supports = []
        for item in evidence:
            current = {"name": item} if isinstance(item, str) else dict(item)
            blob = f"{current.get('name', '')} {current.get('content', '')} {current.get('description', '')}"
            overlap = claim_tokens & _tokens(blob)
            if overlap:
                supports.append({"evidence_id": current.get("evidence_id") or current.get("name"), "overlap": sorted(overlap)[:8], "confidence": min(0.9, 0.4 + 0.1 * len(overlap))})
        mappings.append({"claim": claim_text, "supports": supports, "supported": bool(supports)})
    unsupported = [item["claim"] for item in mappings if not item["supported"]]
    return {
        "mappings": mappings,
        "unsupported_claims": unsupported,
        "warnings": ["no claims supplied"] if not claims else (["some claims have no overlapping evidence tokens"] if unsupported else []),
    }
