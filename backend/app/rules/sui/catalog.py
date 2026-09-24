from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.cards import SPECIAL_CARD_SPECS, SUI_RANK_ORDER


@dataclass(frozen=True)
class SuiRule:
    kind: str
    display_name: str
    timing: str
    source_text: str
    implementation_status: str


SUI_RULES: dict[str, SuiRule] = {
    spec.kind: SuiRule(
        kind=spec.kind,
        display_name=spec.display_name or spec.kind,
        timing="field" if spec.kind == "cannot" else "see" if spec.kind in {"sui_xiang", "fuzhou"} else "reaction" if spec.kind in {"zuole", "xi"} else "main_or_claim",
        source_text=spec.source_text or "",
        implementation_status="specified",
    )
    for spec in SPECIAL_CARD_SPECS
}


def higher_sui_rank(candidate_kind: str, target_kind: str) -> bool:
    try:
        return SUI_RANK_ORDER.index(candidate_kind) < SUI_RANK_ORDER.index(target_kind)
    except ValueError:
        return False

