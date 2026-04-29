[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "your-api-test-project"
version = "0.1.0"
description = "API自动化测试项目"
requires-python = ">=3.9"
dependencies = [
    "requests>=2.0",
    "PyYAML>=6.0",
    "jsonpath-ng>=1.5",
    "allure-pytest>=2.0",
]

[project.optional-dependencies]
pytest = [
    "pytest>=7.0",
    "allure-pytest>=2.0",
    "pytest-ordering>=0.6",
]

[tool.setuptools.packages.find]
include = ["api_test_framework*"]

