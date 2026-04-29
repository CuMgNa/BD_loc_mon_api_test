"""run.py — 一键运行入口

执行流程：
1. pytest 跑用例，生成原始结果到 ./temps
2. allure generate 把原始结果转换为静态报告到 ./reports
3. allure open 启动本地 HTTP 服务打开报告
   （必须用 HTTP 服务打开，否则浏览器会因 CORS 限制
    无法加载 reports/data 下的 json，页面会一直 Loading）
"""
import os
import time
import pytest

if __name__ == '__main__':
    pytest.main()
    time.sleep(2)

    os.system("allure generate ./temps -o ./reports --clean")
    print("\n报告已生成: ./reports/index.html")

    print("正在启动 Allure 本地服务，请勿直接双击 index.html ...")
    os.system("allure open ./reports")
