"""Project budgets without double counting.

`project_budget_schedule` repeats a budget once per linked PID, and a few FMS IDs have two managing
agencies with separate budgets (DDC $70.2M and DOT $0.9M on HWK1669A). A project's budget is the
sum, over its managing agencies, of each agency's record in the latest snapshot the project appears in.
"""

BUDGETS = """
    with rec as (
        select fms_id, managing_agency, reporting_period,
               any_value(total_budget) as budget, any_value(spend_to_date) as spend
        from project_budget_schedule group by all),
    last as (select fms_id, max(reporting_period) as last_period from rec group by 1)
    select r.fms_id, sum(r.budget) as budget, sum(r.spend) as spend, l.last_period
    from rec r join last l on r.fms_id = l.fms_id and r.reporting_period = l.last_period
    group by r.fms_id, l.last_period"""


def project_budgets(con) -> dict[str, tuple[float, float, int]]:
    """fms_id -> (budget, spend to date, last reporting period)."""
    return {f: (b or 0.0, s or 0.0, p) for f, b, s, p in con.execute(BUDGETS).fetchall()}
