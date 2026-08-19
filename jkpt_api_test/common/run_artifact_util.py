# common/run_artifact_util.py
# 开跑前清 Allure raw，避免 temps/ 与 stray allure-results/ 跨轮叠加。
# 不删 reports/（HTML）；不在 session 结束时删（run.py 还要用 temps generate）。

import shutil
from pathlib import Path

ALLURE_RAW_DIR_NAMES = ("temps", "allure-results")


def wipe_allure_raw_dirs(root) -> list:
    """删除 root 下 temps/ 与 allure-results/。返回实际动手的目录名。缺目录当成功。"""
    root_path = Path(root)
    wiped = []
    for name in ALLURE_RAW_DIR_NAMES:
        path = root_path / name
        if not path.is_dir():
            continue
        shutil.rmtree(path, ignore_errors=True)
        wiped.append(name)
    return wiped
