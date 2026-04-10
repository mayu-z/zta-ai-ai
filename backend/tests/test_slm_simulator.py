from app.slm.simulator import SLMSimulator


def test_trim_after_last_slot_sentence_keeps_all_slots() -> None:
    content = (
        "Across institutions, [SLOT_1] students are enrolled. "
        "The year-over-year trend is [SLOT_2]. "
        "This trailing fragment should be dropped"
    )

    trimmed = SLMSimulator._trim_after_last_slot_sentence(content)

    assert "[SLOT_1]" in trimmed
    assert "[SLOT_2]" in trimmed
    assert "trailing fragment" not in trimmed
    assert trimmed.endswith(".")


def test_ensure_required_slots_appends_missing_slots() -> None:
    template = "Total enrollment is [SLOT_1]."

    ensured = SLMSimulator._ensure_required_slots(
        template,
        ["[SLOT_1]", "[SLOT_2]"],
    )

    assert "[SLOT_1]" in ensured
    assert "[SLOT_2]" in ensured
    assert "Include also" in ensured
