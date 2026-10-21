import pytest

from anonymizer import core, guard, regex_detect, store
from anonymizer.pseudonymize import pseudonymize, reidentify
from anonymizer.regex_detect import Span


def spans_for(text, items):
    out = []
    for s, t in items:
        i = text.index(s)
        out.append(Span(i, i + len(s), t, s, "llm"))
    return out


def test_regex_finds_structured_ids():
    text = ("Reach me at jon.reyes@student.example.edu or (713) 555-0142. UH ID 1834567, "
            "award 80NSSC99K1234, cost center G0599123, speedtype 74512, SSN 912-34-5678.")
    types = {s.type for s in regex_detect.detect(text)}
    assert {"EMAIL", "PHONE", "ID_NUMBER", "GRANT_NUMBER", "COST_CENTER", "SSN"} <= types


def test_same_person_same_token_and_name_parts_expanded():
    text = "Met with Jonathan Reyes today. Reyes said the commute is long. Jonathan agreed."
    san, mapping, _ = pseudonymize(text, spans_for(text, [("Jonathan Reyes", "PERSON")]))
    assert "Reyes" not in san and "Jonathan" not in san
    assert san.count("[PERSON_1]") == 3
    assert "long" in san  # ordinary words untouched


def test_common_word_name_part_replaced_only_when_capitalised():
    text = "Grant Whitfield needs funds. The grant budget is fine. Grant will take over. Ask Whitfield."
    san, mapping, audit = pseudonymize(text, spans_for(text, [("Grant Whitfield", "PERSON")]))
    assert "The grant budget" in san
    assert "Grant" not in san and "Whitfield" not in san
    blocks, warns = guard.check(text, san, mapping, audit["common_word_parts"])
    assert not blocks


def test_round_trip_tolerates_token_variants():
    text = "Dr. Marchetti wrote to Jonathan Reyes."
    san, mapping, _ = pseudonymize(text, spans_for(text, [("Marchetti", "PERSON"), ("Jonathan Reyes", "PERSON")]))
    reply = "Tell [PERSON_2] that Person_1 approved it; [PERSON 2] should reply."
    out, unknown = reidentify(reply, mapping)
    assert out == "Tell Jonathan Reyes that Marchetti approved it; Jonathan Reyes should reply."
    assert not unknown


def test_unknown_tokens_reported():
    out, unknown = reidentify("ask [PERSON_9]", {})
    assert unknown == ["[PERSON_9]"]


def test_guard_blocks_export_control_marker():
    r = core.anonymize("EXPORT CONTROLLED - ITAR. Test data for Jonathan.", detector="regex")
    assert not r.ok


def test_guard_blocks_leftover_lowercase_name():
    text = "Jonathan Reyes asked. signed: jonathan reyes"
    san, mapping, audit = pseudonymize(text, spans_for(text, [("Jonathan Reyes", "PERSON")]))
    blocks, _ = guard.check(text, san, mapping)
    assert not blocks  # case-insensitive full-surface replacement covers it
    assert "jonathan" not in san.lower()


def test_guard_messages_never_contain_values():
    text = "Call 713-555-0101 now."
    blocks, _ = guard.check(text, text, {})
    assert blocks and all("555" not in b for b in blocks)


def test_mapping_encryption_round_trip(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    monkeypatch.setenv("ANONYMIZER_PASSPHRASE", "test-only")
    m = {"[PERSON_1]": {"type": "PERSON", "canonical": "X", "surfaces": ["X"], "sources": []}}
    p = store.save(m, tmp_path / "m.json", encrypt=True)
    assert b"canonical" not in p.read_bytes()
    assert store.load(p) == m
    assert oct(p.stat().st_mode)[-3:] == "600"


def test_regex_type_wins_and_misspelling_links():
    text = "Siobhan McAllister (713) 555-0109. Spelled McAlliste on the transcript."
    sp = regex_detect.detect(text) + spans_for(text, [("Siobhan McAllister", "PERSON"), ("McAlliste", "PERSON"),
                                                     ("(713) 555-0109", "ID_NUMBER")])
    san, mapping, _ = pseudonymize(text, sp)
    assert "[PHONE_1]" in san and "ID_NUMBER" not in san
    assert san.count("[PERSON_1]") == 2 and "[PERSON_2]" not in san


def test_gazetteer_places_and_counties():
    text = "Commutes from Pearland; site in Galveston County. Starts Spring 2027 in Houston."
    found = {s.text for s in regex_detect.detect(text) if s.type == "LOCATION"}
    assert {"Pearland", "Galveston County"} <= found and "Spring" not in found
    san, _, _ = pseudonymize(text, regex_detect.detect(text))
    assert san == "Commutes from [LOCATION_1]; site in [LOCATION_2]. Starts Spring 2027 in Houston."


def test_title_stays_in_text_and_labels_stay_readable():
    text = "To: Dr. Samuel Oyelaran\nRe: award 80NSSC99K3602 (cost center G0599274)"
    sp = regex_detect.detect(text) + spans_for(text, [("Dr. Samuel Oyelaran", "PERSON"),
                                                     ("award 80NSSC99K3602", "ID_NUMBER"),
                                                     ("cost center G0599274", "ID_NUMBER")])
    san, mapping, _ = pseudonymize(text, sp)
    assert san == "To: Dr. [PERSON_1]\nRe: award [GRANT_NUMBER_1] (cost center [COST_CENTER_1])"
    out, _ = reidentify("Dear Dr. [PERSON_1]", mapping)
    assert out == "Dear Dr. Samuel Oyelaran"


def test_remote_ollama_refused(monkeypatch):
    from anonymizer import llm_detect
    monkeypatch.setattr(llm_detect, "OLLAMA_URL", "http://192.0.2.10:11434")
    with pytest.raises(llm_detect.LLMDetectError):
        llm_detect.detect("Jonathan Reyes")
    monkeypatch.setattr(llm_detect, "OLLAMA_URL", "http://localhost:11434")
    llm_detect.check_host()  # no error


def test_common_word_first_name_alone_joins_full_name():
    text = "Met with Grant Whitfield. Grant is a junior."
    san, _, _ = pseudonymize(text, spans_for(text, [("Grant Whitfield", "PERSON"), ("Grant", "PERSON")]))
    assert san == "Met with [PERSON_1]. [PERSON_1] is a junior."
