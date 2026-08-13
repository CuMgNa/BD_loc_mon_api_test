"""
run.py — 一键运行入口
用法: python run.py
效果: 执行所有pytest用例 → 等待3秒 → 生成Allure HTML报告
"""
import os, time, pytest

if __name__ == '__main__':
    pytest.main()                                         # 运行测试
    time.sleep(3)                                         # 等待报告文件写入
    os.system("allure generate ./temps -o ./reports --clean")  # 生成HTML报告
    print("\n✅ 报告已生成: ./reports/index.html")
    # 如需自动打开浏览器，取消下面一行:
    # os.system("allure open ./reports")
