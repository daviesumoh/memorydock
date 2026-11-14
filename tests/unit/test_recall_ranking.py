from datetime import UTC, datetime

from memorydock_core.memory import rules
from memorydock_core.recall import ranking

NOW = datetime(2026, 11, 14, tzinfo=UTC)
KEYS = ["org:halcyon", "project:halcyon/lantern", "user:halcyon/usr_rosa"]


def build(work=True, focus=None):
    return ranking.pipeline(
        "onboarding", tenant="halcyon", keys=KEYS, work_session=work, focus_key=focus,
        now=NOW, limit=24,
    )  # fmt: skip


def branches(p):
    pipes = p[0]["$rankFusion"]["input"]["pipelines"]
    return pipes["vec"][0]["$vectorSearch"], pipes["text"][0]["$search"]["compound"]["filter"]


def test_every_eligibility_rule_is_a_prefilter_in_both_branches():
    vec, text = branches(build(work=True))
    assert vec["filter"] == {
        "tenant_id": "halcyon",
        "scope_key": {"$in": KEYS},
        "status": {"$in": ["active", "conflict", "disputed"]},
        "inject_in_work": True,
    }
    assert {"equals": {"path": "tenant_id", "value": "halcyon"}} in text
    assert {"in": {"path": "scope_key", "value": KEYS}} in text
    assert {"in": {"path": "status", "value": ["active", "conflict", "disputed"]}} in text
    assert {"equals": {"path": "inject_in_work", "value": True}} in text


def test_proposed_is_never_recallable():
    assert "proposed" not in rules.RECALLABLE
    vec, _ = branches(build())
    assert "proposed" not in vec["filter"]["status"]["$in"]


def test_non_work_sessions_skip_the_work_filter():
    vec, text = branches(build(work=False))
    assert "inject_in_work" not in vec["filter"]
    assert all(f.get("equals", {}).get("path") != "inject_in_work" for f in text)


def test_branches_contain_no_project_stage():
    pipes = build()[0]["$rankFusion"]["input"]["pipelines"]
    for stages in pipes.values():
        assert all("$project" not in s for s in stages)


def test_live_documents_are_rechecked_right_after_search():
    match = build()[1]["$match"]
    assert match["tenant_id"] == "halcyon"
    assert match["scope_key"] == {"$in": KEYS}
    assert match["status"] == {"$in": list(rules.RECALLABLE)}
    assert {"validity.expires_at": {"$gt": NOW}} in match["$or"]


def test_weights_come_from_the_rules_tables():
    stages = build()
    score = next(s for s in stages if "_score" in s.get("$addFields", {}))["$addFields"]["_score"]
    factors = score["$multiply"]
    trust = factors[1]["$switch"]["branches"]
    assert {(b["case"]["$eq"][1], b["then"]) for b in trust} == set(rules.TRUST_WEIGHT.items())
    recency_types = {b["case"]["$eq"][1] for b in factors[2]["$switch"]["branches"]}
    assert recency_types == {t for t, hl in rules.HALF_LIFE_DAYS.items() if hl}


def test_focus_project_outranks_other_projects():
    def project_weight(stages):
        score = next(s for s in stages if "_score" in s.get("$addFields", {}))
        scope = score["$addFields"]["_score"]["$multiply"][3]["$switch"]["branches"]
        return next(b["then"] for b in scope if b["case"]["$eq"][1] == "project")

    assert project_weight(build(focus=None)) == 1.0
    focused = project_weight(build(focus="project:halcyon/lantern"))
    assert focused["$cond"][1:] == [1.0, rules.OTHER_PROJECT_WEIGHT]


def test_results_are_cut_sorted_and_limited():
    stages = build()
    assert {"$limit": 24} in stages
    assert {"$sort": {"_score": -1, "_id": 1}} in stages
    project = stages[-1]["$project"]
    assert "embed_text" not in project and project["score"] == "$_score"
