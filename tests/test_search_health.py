from project_opener.core import models as M
from project_opener.core.health import check_project
from project_opener.core.pathvars import PathResolver
from project_opener.core.search import search_everything, search_projects, subsequence_score


def test_subsequence_scores_rank_sensibly():
    assert subsequence_score("ant", "ANTEO") == 1.0
    assert subsequence_score("teo", "ANTEO") > subsequence_score("ao", "ANTEO") > 0
    assert subsequence_score("zzz", "ANTEO") == 0.0


def test_search_projects_prefers_pinned_and_prefix():
    a = M.Project(name="ANTEO isos")
    b = M.Project(name="Anteo handover", pinned_at="2026-01-01")
    hits = search_projects("ant", [a, b])
    assert hits[0].project is b


def test_search_everything_finds_items_and_sets():
    p = M.Project(name="P12513", items=[M.Item(path=r"Z:\x\Line list.xlsx")])
    p.launch_sets.append(M.LaunchSet(name="Morning start", item_ids=[p.items[0].id]))
    hits = search_everything("line", [p])
    assert any(h.kind == "item" for h in hits)
    hits = search_everything("morn", [p], actions=[("new", "New project", "fa5s.plus")])
    assert hits[0].kind == "set"


def test_health_statuses(tmp_path):
    ok = tmp_path / "ok.txt"
    ok.write_text("x", encoding="utf-8")
    p = M.Project(name="h", items=[M.Item(path=str(ok)), M.Item(path=str(tmp_path / "nope")),
                                  M.Item(path="{X}/y"), M.Item(path="https://a.b", kind="url")])
    h = check_project(p, PathResolver({}, drive_map={}))
    assert [i.status for i in h.items] == ["ok", "missing", "variable", "ok"]
    assert 0 < h.score < 1
