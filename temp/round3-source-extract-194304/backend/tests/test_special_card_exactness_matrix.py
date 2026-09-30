from pathlib import Path

from backend.app.engine.special_effects import SPECIAL_RULES, SUPPORTED_SPECIAL_IDS


CARD_STATUSES = {
    "wang": "CONSERVATIVE_ACCEPTED",
    "ji": "EXACT",
    "yu": "EXACT",
    "yi": "EXACT",
    "zuole": "CONSERVATIVE_ACCEPTED",
    "xi": "CONSERVATIVE_ACCEPTED",
    "nian": "EXACT",
    "sui_xiang": "EXACT",
    "shu": "EXACT",
    "chongyue": "EXACT",
    "ling": "EXACT",
    "cannot": "EXACT",
    "fuzhou": "CONSERVATIVE_ACCEPTED",
}


def test_exactness_matrix_covers_all_thirteen_special_and_field_cards():
    assert set(CARD_STATUSES) == SUPPORTED_SPECIAL_IDS
    assert set(SPECIAL_RULES) == SUPPORTED_SPECIAL_IDS
    assert len(CARD_STATUSES) == 13
    assert "CONSERVATIVE" not in set(CARD_STATUSES.values())
    assert "MISSING" not in set(CARD_STATUSES.values())


def test_conservative_accepted_cards_are_documented_with_impact_and_tests():
    docs = Path("docs/SPECIAL_CARD_RULES_FROM_CARDS_ZIP.md").read_text(encoding="utf-8")
    for card_id, status in CARD_STATUSES.items():
        if status != "CONSERVATIVE_ACCEPTED":
            continue
        section_start = docs.index(f"### `{card_id}` - CONSERVATIVE_ACCEPTED")
        section = docs[section_start : docs.find("\n### ", section_start + 1) if "\n### " in docs[section_start + 1 :] else len(docs)]
        assert "Source rule:" in section
        assert "Project rule:" in section
        assert "Impact:" in section
        assert "Test coverage:" in section
