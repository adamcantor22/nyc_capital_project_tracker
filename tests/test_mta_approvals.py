import re

import pytest

from fetch_mta_docs import DOCUMENTS, OUT
from mta_growth import PLANS, agency_amendments, approvals, fragments, mega_amendments


def test_fragments_carry_their_page():
    assert fragments("p2: On April 28, 2010, the Board | p13: approved") == [(2, "On April 28, 2010, the Board"),
                                                                            (13, "approved")]


def test_approval_rows_name_a_plan_dates_and_a_fetched_document():
    rows = approvals()
    assert rows
    day = re.compile(r"\d{4}-\d{2}(-\d{2})?")
    for plan, step, outcome, board, cprb, total, _, doc, _, quote in rows:
        assert plan in PLANS.values() and step and outcome and (total is None or total > 1e10)
        assert (not board or day.fullmatch(board)) and (cprb is None or day.fullmatch(cprb))
        assert doc in DOCUMENTS and fragments(quote) and len(fragments(quote)) == quote.count(" | ") + 1


NUMBER = re.compile(r"\(?-?\$?\d[\d,]*(?:\.\d)?\)?")


def numbers(quote: str, line: str) -> list[float]:
    (_, text), = fragments(quote)
    text = text[len(line):]
    return [float(n.strip("()$").replace(",", "").replace("$", "")) * (-1 if n.startswith("(") else 1)
            for n in NUMBER.findall(text)]


def test_mega_amendment_lines_hold_their_numbers_and_add_up():
    """Each quoted line holds the row's numbers; its printed change is proposed minus the earliest column (or, in the
    2010 book, prior plans plus 2010-14 make the project total); each table's lines add up to its total line.
    A row whose note records a printing error is exempt."""
    sums = {}
    for _, _, _, step, line, key, _, earlier, prior, proposed, doc, _, quote, note in mega_amendments():
        sums.setdefault((doc, step), [0.0, None])
        if key == "total":
            sums[(doc, step)][1] = proposed
        else:
            sums[(doc, step)][0] += proposed
        if (note or "").startswith("printed"):
            continue
        n = numbers(quote, line)
        assert all(v is None or round(v / 1e6, 1) in n for v in (earlier, prior, proposed)), (doc, line)
        if prior is None and earlier is None and len(n) == 1:  # a plan book prints one figure per line
            continue
        assert abs(n[0] + n[-1] - n[-2]) < 0.15 or abs(n[0] + n[1] - n[2]) < 1.5, (doc, line, n)
    assert all(abs(lines - total) < 0.6e6 for lines, total in sums.values()), sums


def test_mega_amendment_steps_are_approvals_and_consecutive_books_agree():
    """Steps name rows of mta_program_approvals.csv; a step printed by two books (proposed in one, prior in the next)
    has one value per line, a line missing from one book being 0 (a printing error is corrected in `proposed` and
    noted)."""
    steps = {(a[0], a[1]) for a in approvals()}
    printed = {}
    for plan, prior_step, _, step, _, key, _, _, prior, proposed, doc, _, _, _ in mega_amendments():
        assert (plan, step) in steps and (prior_step is None or (plan, prior_step) in steps)
        printed.setdefault((plan, step), {}).setdefault(doc, {})[key] = proposed
        if prior_step:
            printed.setdefault((plan, prior_step), {}).setdefault(doc, {})[key] = prior
    compared = 0
    for (plan, step), books in printed.items():
        if len(books) < 2:
            continue
        compared += 1
        first, *rest = books.values()
        for other in rest:  # a line new in a later book is printed there with a prior of 0
            assert all(other.get(k, 0) == first.get(k, 0) for k in first.keys() | other.keys()), (plan, step)
    assert compared >= 5  # when set: 5 steps printed by two books


CORE = {"nyct", "nyct_bus", "lirr", "mnr", "bus", "security", "dr_restoration", "dr_mitigation", "interagency"}
BT = {"bt", "bt_dr_restoration", "bt_dr_mitigation"}


def test_agency_amendment_tables_add_up_and_agree():
    """Each row's value is in its quoted line; each printed change is its two columns' difference; core lines make
    the core subtotal, core plus expansion the CPRB total, CPRB plus B&T the program total; books printing the same
    step agree; each step's totals equal mta_program_approvals.csv. Tolerances are the books' rounding."""
    rows = agency_amendments()
    approved = {(a[0], a[1]): a for a in approvals()}
    amounts = {}
    for plan, doc, _, _, kind, step, _, line, key, value, quote, _ in rows:
        assert (plan, step) in approved, (plan, step)
        text = " ".join(t for _, t in fragments(quote))
        n = [float(x.strip("()$").replace(",", "").replace("$", "")) * (-1 if x.startswith("(") else 1)
             for x in NUMBER.findall(text.replace(line, "", 1))]
        assert value / 1e6 in n, (doc, line, value)
        if kind == "amount":
            amounts.setdefault((plan, doc, step), {})[key] = value / 1e6
    for plan, doc, _, _, kind, step, frm, _, key, value, _, _ in rows:
        if kind == "change":
            assert abs(amounts[(plan, doc, step)][key] - amounts[(plan, doc, frm)][key] - value / 1e6) <= 1, (doc, key)
    steps = {}
    for (plan, doc, step), a in amounts.items():
        core = sum(a.get(k, 0) for k in CORE)
        assert abs(core - a.get("core_subtotal", core)) <= 2, (doc, step)
        assert abs(core + a["expansion"] - a["cprb_total"]) <= 2, (doc, step)
        assert abs(a["cprb_total"] + sum(a.get(k, 0) for k in BT) - a["total"]) <= 2, (doc, step)
        _, _, _, _, _, total, cprb, *_ = approved[(plan, step)]
        assert total is None or abs(total / 1e6 - a["total"]) <= 1, (doc, step)
        assert cprb is None or abs(cprb / 1e6 - a["cprb_total"]) <= 1, (doc, step)
        for key, v in a.items():
            steps.setdefault((plan, step, key), []).append(v)
    shared = [vs for vs in steps.values() if len(vs) > 1]
    assert all(max(vs) - min(vs) <= 1 for vs in shared)
    assert len({k[:2] for k, vs in steps.items() if len(vs) > 1}) >= 5  # when set: 5 steps printed by two books


@pytest.mark.data
def test_every_quoted_fragment_is_on_its_page():
    """Each fragment of mta_program_approvals.csv, mta_mega_amendments.csv and mta_agency_amendments.csv appears,
    whitespace aside, on the cited page of the fetched PDF."""
    import logging

    from pypdf import PdfReader
    logging.disable(logging.WARNING)
    readers = {}
    missing = []
    quoted = ([(r[7], r[1], r[9]) for r in approvals()] + [(r[10], r[3], r[12]) for r in mega_amendments()]
              + [(r[1], r[5], r[10]) for r in agency_amendments()])
    for doc, step, quote in quoted:
        path = OUT / f"{doc}.pdf"
        if not path.exists():
            pytest.skip("pipeline/fetch_mta_docs.py not run")
        reader = readers.setdefault(doc, PdfReader(path))
        for page, text in fragments(quote):
            if " ".join(text.split()) not in " ".join((reader.pages[page - 1].extract_text() or "").split()):
                missing.append((doc, step, page, text[:60]))
    assert missing == []
