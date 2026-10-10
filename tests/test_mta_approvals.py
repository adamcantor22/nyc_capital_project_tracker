import re

import pytest

from fetch_mta_docs import DOCUMENTS, OUT
from mta_growth import PLANS, approvals, fragments, mega_amendments


def test_fragments_carry_their_page():
    assert fragments("p2: On April 28, 2010, the Board | p13: approved") == [(2, "On April 28, 2010, the Board"),
                                                                            (13, "approved")]


def test_approval_rows_name_a_plan_dates_and_a_fetched_document():
    rows = approvals()
    assert rows
    day = re.compile(r"\d{4}-\d{2}(-\d{2})?")
    for plan, step, outcome, board, cprb, total, _, doc, _, quote in rows:
        assert plan in PLANS.values() and step and outcome and (total is None or total > 1e10)
        assert day.fullmatch(board) and (cprb is None or day.fullmatch(cprb))
        assert doc in DOCUMENTS and fragments(quote) and len(fragments(quote)) == quote.count(" | ") + 1


NUMBER = re.compile(r"\(?-?\$?[\d,]+\.\d\)?")


def test_mega_amendment_steps_are_approvals_and_consecutive_books_agree():
    """Steps name rows of mta_program_approvals.csv; a step printed by two books (proposed in one, prior in the next)
    has one value per line, unless a note records a printing error; quoted lines hold the row's numbers."""
    steps = {(a[0], a[1]) for a in approvals()}
    rows = mega_amendments()
    printed = {}
    for plan, prior_step, _, step, line, _, prior, proposed, _, _, quote, note in rows:
        assert (plan, step) in steps and (prior_step is None or (plan, prior_step) in steps)
        (_, text), = fragments(quote)
        values = {round(float(n.strip("()$").replace(",", "").replace("$", "")) * 1e6) for n in NUMBER.findall(text)}
        assert prior is None or prior in values, (step, line)
        assert proposed in values or (note or "").startswith("printed"), (step, line)
        printed.setdefault((plan, step, line), set()).add(proposed)
        if prior_step:
            printed.setdefault((plan, prior_step, line), set()).add(prior)
    assert [k for k, v in printed.items() if len(v) > 1] == []


@pytest.mark.data
def test_every_quoted_fragment_is_on_its_page():
    """Each fragment of mta_program_approvals.csv and mta_mega_amendments.csv appears, whitespace aside, on the cited
    page of the fetched PDF."""
    import logging

    from pypdf import PdfReader
    logging.disable(logging.WARNING)
    readers = {}
    missing = []
    quoted = [(r[7], r[1], r[9]) for r in approvals()] + [(r[8], r[3], r[10]) for r in mega_amendments()]
    for doc, step, quote in quoted:
        path = OUT / f"{doc}.pdf"
        if not path.exists():
            pytest.skip("pipeline/fetch_mta_docs.py not run")
        reader = readers.setdefault(doc, PdfReader(path))
        for page, text in fragments(quote):
            if " ".join(text.split()) not in " ".join((reader.pages[page - 1].extract_text() or "").split()):
                missing.append((doc, step, page, text[:60]))
    assert missing == []
