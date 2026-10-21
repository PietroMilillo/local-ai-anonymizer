"""Synthetic test corpus: advising notes, grade-appeal emails, grant budget memos, sponsor reports.

Everything is invented. Phone numbers use the fictional 555-01xx range, SSN-like
numbers the never-issued 9xx range, e-mail addresses example.edu / example.com,
award numbers a "99" year. Every identifier planted in a document is recorded in
truth.json with its exact surface form and the adversarial case it exercises.

  python -m synth.generate --n 10 --seed 7 --out corpus
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

# (first, last, nickname). The last three are first names that are also common words.
STUDENTS = [
    ("Jonathan", "Reyes", "Jon"), ("Mariana", "Okonkwo", "Mari"), ("Oluwaseun", "Adeyemi", "Seun"),
    ("Priyanka", "Venkataraman", "Priya"), ("Xiaoling", "Zhou", "Ling"), ("Mateo", "Castellanos", "Teo"),
    ("Abigail", "Thornbury", "Abby"), ("Dmitri", "Volkonsky", "Dima"), ("Fatima", "Al-Rashidi", "Fati"),
    ("Kwabena", "Asante-Boateng", "Kobby"), ("Siobhan", "McAllister", "Shiv"), ("Nguyen", "Thi Lan", "Lan"),
    ("Rafael", "Quintanilla", "Rafa"), ("Ingrid", "Solberg", "Inga"), ("Tomasz", "Wierzbicki", "Tomek"),
    ("Grant", "Whitfield", None), ("Hope", "Delacroix", None), ("Will", "Okafor", None),
]
FACULTY = [
    ("Evelyn", "Marchetti"), ("Samuel", "Oyelaran"), ("Lucia", "Ferreira-Haas"), ("Tobias", "Lindqvist"),
    ("Hannah", "Szymanski"), ("Rohan", "Iyer-Bennett"), ("Camila", "Etxeberria"), ("Desmond", "Achterberg"),
]
PARTNERS = ["Brazos Geotech LLC", "Gulf Coast Survey Partners", "Rice University", "Texas A&M University",
            "Bayou Structural Analytics Inc.", "Lone Star Remote Sensing Co."]
# Held-out towns: real Texas places deliberately absent from anonymizer/places.py, so the
# held-out corpus measures what the model finds without the gazetteer's help.
HELDOUT_PLACES = ["Wharton", "Bay City", "Navasota", "Brenham", "El Campo", "Liberty", "Hempstead"]
PLACES = ["Pearland", "Katy", "Sugar Land", "Galveston County", "Brazoria County", "Baytown", "Clear Lake"]
STREETS = ["Bellmont Ave", "Wroxton Rd", "Holcombe Blvd", "Kirby Dr", "Telephone Rd", "Ashby Street"]
MAJORS = ["civil engineering", "geomatics", "environmental engineering", "construction management"]
MONTHS = ["January", "February", "March", "April", "September", "October", "November", "December"]


class Doc:
    def __init__(self):
        self.parts, self.truth = [], []

    def plant(self, value: str, typ: str, case: str = "direct") -> str:
        self.truth.append({"value": value, "type": typ, "case": case})
        return value


def _uhid(r):
    return str(r.randint(1_000_000, 2_999_999))


def _phone(r):
    return r.choice(["(713) 555-01%02d", "713-555-01%02d", "832.555.01%02d", "+1 281 555 01%02d"]) % r.randint(0, 99)


def _date(r, year=2026):
    return f"{r.choice(MONTHS)} {r.randint(1, 28)}, {year}"


def advising_note(r, s, f):
    first, last, nick = s
    d = Doc()
    uid, email = _uhid(r), f"{first.lower()}.{last.lower().replace(' ', '')}@student.example.edu"
    phone, place, major = _phone(r), r.choice(PLACES), r.choice(MAJORS)
    gpa = f"{r.uniform(1.6, 2.4):.2f}"
    head = r.choice(["upper", "plain"])
    title = (d.plant(f"{last.upper()}, {first.upper()}", "PERSON", "all_caps_header") if head == "upper"
             else d.plant(f"{first} {last}", "PERSON"))
    d.parts.append(f"ADVISING NOTE - {title}\nDate: {d.plant(_date(r), 'DATE', 'quasi')}\n")
    d.parts.append(
        f"Met with {d.plant(f'{first} {last}', 'PERSON')} (UH ID {d.plant(uid, 'ID_NUMBER')}, "
        f"{d.plant(email, 'EMAIL')}) to discuss academic probation. {d.plant(first, 'PERSON', 'first_name_alone')} "
        f"is a junior in {major} with a cumulative GPA of {gpa}, commuting daily from {d.plant(place, 'LOCATION')}.")
    if nick:
        d.parts.append(f"{d.plant(nick, 'PERSON', 'nickname')} said the commute and a part-time job at "
                       f"{d.plant(r.choice(PARTNERS[:2] + PARTNERS[4:]), 'ORG')} are the main problems.")
    d.parts.append(
        f"Faculty mentor is Dr. {d.plant(f[1], 'PERSON', 'surname_alone')}, who suggested reducing the load to "
        f"12 hours next term. Follow up by phone at {d.plant(phone, 'PHONE')}.")
    if r.random() < 0.5:
        d.parts.append(f"Note: {d.plant(last, 'PERSON', 'possessive')}'s paperwork for the "
                       f"financial aid appeal is due {d.plant(_date(r), 'DATE', 'quasi')}.")
    if r.random() < 0.5:
        d.parts.append(f"(spelled \"{d.plant(last[:-1] if len(last) > 4 else last + 'e', 'PERSON', 'misspelling')}\" "
                       f"on the transfer transcript)")
    return d


def grade_appeal(r, s, f):
    first, last, nick = s
    d = Doc()
    email = f"{first[0].lower()}{last.lower().replace(' ', '').replace('-', '')}{r.randint(1, 9)}@student.example.edu"
    ta = r.choice([x for x in STUDENTS if x != s])
    uid = _uhid(r)
    d.parts.append(f"From: \"{d.plant(f'{last}, {first}', 'PERSON', 'surname_first')}\" <{d.plant(email, 'EMAIL')}>")
    d.parts.append(f"To: Dr. {d.plant(f'{f[0]} {f[1]}', 'PERSON')}")
    d.parts.append(f"Subject: Grade appeal CIVE 3331 - {d.plant(last, 'PERSON', 'name_in_subject')} - "
                   f"{d.plant(uid, 'ID_NUMBER')}\n")
    d.parts.append(f"Dear Dr. {d.plant(f[1], 'PERSON', 'surname_alone')},")
    d.parts.append(
        f"I am writing to appeal my grade on Exam 2 ({d.plant(_date(r), 'DATE', 'quasi')}). Question 4 was graded by "
        f"the TA, {d.plant(f'{ta[0]} {ta[1]}', 'PERSON', 'third_party')}, and I believe partial credit applies. "
        f"My accommodation letter from the disability office allows extra time, which I did not receive.")
    if r.random() < 0.5:
        d.parts.append(f"My cougarnet username is {d.plant(email.split('@')[0], 'ID_NUMBER', 'username')} if you "
                       f"need to check the submission.")
    sig = r.choice(["nick", "lower", "initial", "full"])
    if sig == "nick" and nick:
        d.parts.append(f"Thanks,\n{d.plant(nick, 'PERSON', 'nickname')}")
    elif sig == "lower":
        d.parts.append(f"thanks\n{d.plant(f'{first.lower()} {last.lower()}', 'PERSON', 'lowercase')}")
    elif sig == "initial":
        d.parts.append(f"Best,\n{d.plant(f'{first[0]}. {last}', 'PERSON', 'initial')}")
    else:
        d.parts.append(f"Best regards,\n{d.plant(f'{first} {last}', 'PERSON')}")
    return d


def budget_memo(r, s, f):
    first, last, nick = s
    d = Doc()
    pi, copi = f, r.choice([x for x in FACULTY if x != f])
    award = f"80NSSC99K{r.randint(1000, 9999)}"
    cc, st = f"G0599{r.randint(100, 999)}", str(r.randint(70000, 79999))
    partner = r.choice(PARTNERS)
    amt = r.randint(18, 95) * 1000 + r.choice([0, 250, 500])
    d.parts.append(f"MEMO\nTo: Office of Contracts and Grants\nFrom: Dr. {d.plant(f'{pi[0]} {pi[1]}', 'PERSON')}\n"
                   f"Re: Rebudget request, award {d.plant(award, 'GRANT_NUMBER')} (cost center "
                   f"{d.plant(cc, 'COST_CENTER')}, speedtype {d.plant(st, 'COST_CENTER')})\n")
    d.parts.append(
        f"The grant budget for Year 2 moves ${amt:,} from travel to graduate student support. The funds will "
        f"cover a stipend for {d.plant(f'{first} {last}', 'PERSON')} through "
        f"{d.plant(_date(r, 2027), 'DATE', 'quasi')}. {d.plant(first if nick is None else nick, 'PERSON', 'first_name_alone' if nick is None else 'nickname')} "
        f"will take over the field campaign in {d.plant(r.choice(PLACES), 'LOCATION')}.")
    d.parts.append(
        f"Co-PI Dr. {d.plant(copi[1], 'PERSON', 'surname_alone')} at {d.plant(partner, 'ORG')} has agreed to the change. "
        f"Subcontract invoices go to {d.plant(f'{r.randint(100, 9999)} {r.choice(STREETS)}', 'ADDRESS')}, Houston, TX.")
    if r.random() < 0.5:
        d.parts.append(f"Questions: {d.plant(_phone(r), 'PHONE')} or "
                       f"{d.plant(f'{pi[1].lower().replace(chr(45), chr(32)).split()[0]}@example.edu', 'EMAIL')}.")
    return d


def sponsor_report(r, s, f):
    first, last, nick = s
    d = Doc()
    other = r.choice([x for x in STUDENTS if x != s])
    award = r.choice([f"80NSSC99K{r.randint(1000, 9999)}", f"HM0476{r.randint(10000, 99999)}99"])
    d.parts.append(f"ANNUAL PROGRESS REPORT\nAward {d.plant(award, 'GRANT_NUMBER')}\n"
                   f"PI: {d.plant(f'{f[0]} {f[1]}', 'PERSON')}, University of Houston\n")
    d.parts.append(
        f"Personnel. PhD student {d.plant(f'{first} {last}', 'PERSON')} completed the InSAR processing chain and "
        f"passed the qualifying exam on {d.plant(_date(r), 'DATE', 'quasi')}. MS student "
        f"{d.plant(f'{other[0]} {other[1]}', 'PERSON')} joined in {r.choice(MONTHS)} 2026.")
    d.parts.append(
        f"Collaboration. We worked with {d.plant(r.choice(PARTNERS), 'ORG')} on corner-reflector installation near "
        f"{d.plant(r.choice(PLACES), 'LOCATION')}. {d.plant(last, 'PERSON', 'surname_alone')} led two field visits.")
    if r.random() < 0.5:
        d.parts.append(f"Data are mirrored at {d.plant(f'https://data.example.edu/{last.lower()}-insar', 'URL')}.")
    if r.random() < 0.4:
        d.parts.append(f"Student SSN for the travel reimbursement was sent separately: "
                       f"{d.plant(f'9{r.randint(10, 99)}-{r.randint(10, 99)}-{r.randint(1000, 9999)}', 'SSN')}.")
    return d


TEMPLATES = {"advising": advising_note, "appeal": grade_appeal, "budget": budget_memo, "report": sponsor_report}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="documents per template")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path("corpus"))
    ap.add_argument("--heldout-places", action="store_true", help="use towns absent from the gazetteer")
    a = ap.parse_args(argv)
    if a.heldout_places:
        PLACES[:] = HELDOUT_PLACES
    r = random.Random(a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    truth = {}
    for name, fn in TEMPLATES.items():
        for i in range(a.n):
            s, f = r.choice(STUDENTS), r.choice(FACULTY)
            d = fn(r, s, f)
            doc_id = f"{name}_{i:02d}"
            (a.out / f"{doc_id}.txt").write_text("\n".join(d.parts) + "\n")
            truth[doc_id] = d.truth
    (a.out / "truth.json").write_text(json.dumps(truth, indent=1))
    n = sum(len(v) for v in truth.values())
    print(f"{len(truth)} documents, {n} planted identifiers -> {a.out}")


if __name__ == "__main__":
    main()
