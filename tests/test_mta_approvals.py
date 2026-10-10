import re

import pytest

from fetch_mta_docs import DOCUMENTS, OUT
from mta_growth import PLANS, approvals, fragments


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


@pytest.mark.data
def test_every_quoted_fragment_is_on_its_page():
    """Each fragment of mta_program_approvals.csv appears, whitespace aside, on the cited page of the fetched PDF."""
    import logging

    from pypdf import PdfReader
    logging.disable(logging.WARNING)
    readers = {}
    missing = []
    for _, step, _, _, _, _, _, doc, _, quote in approvals():
        path = OUT / f"{doc}.pdf"
        if not path.exists():
            pytest.skip("pipeline/fetch_mta_docs.py not run")
        reader = readers.setdefault(doc, PdfReader(path))
        for page, text in fragments(quote):
            if " ".join(text.split()) not in " ".join((reader.pages[page - 1].extract_text() or "").split()):
                missing.append((doc, step, page, text[:60]))
    assert missing == []
