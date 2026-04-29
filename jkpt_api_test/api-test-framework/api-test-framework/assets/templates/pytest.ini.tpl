[pytest]
# 运行参数: -v详细 -s允许print --alluredir报告目录 --clean每轮清空
addopts = -vs --alluredir=./temps --clean-alluredir
# 用例搜索路径
testpaths = ./testcases
# 用例文件匹配规则
python_files = test_*.py

markers =
    run: 控制执行顺序(pytest-ordering)
    first: 第一个运行
    last: 最后一个运行
