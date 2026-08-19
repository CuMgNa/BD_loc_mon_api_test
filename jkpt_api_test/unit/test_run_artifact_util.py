# unit/test_run_artifact_util.py — Allure raw 目录开跑前清理（不进 testpaths）
from common.run_artifact_util import wipe_allure_raw_dirs


def test_wipe_removes_temps_and_allure_results_only(tmp_path):
    (tmp_path / "temps").mkdir()
    (tmp_path / "temps" / "old.json").write_text("{}", encoding="utf-8")
    (tmp_path / "allure-results").mkdir()
    (tmp_path / "allure-results" / "old.json").write_text("{}", encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "index.html").write_text("keep", encoding="utf-8")

    wiped = wipe_allure_raw_dirs(tmp_path)

    assert set(wiped) == {"temps", "allure-results"}
    assert not (tmp_path / "temps").exists()
    assert not (tmp_path / "allure-results").exists()
    assert (reports / "index.html").read_text(encoding="utf-8") == "keep"


def test_wipe_missing_dirs_is_noop(tmp_path):
    assert wipe_allure_raw_dirs(tmp_path) == []
