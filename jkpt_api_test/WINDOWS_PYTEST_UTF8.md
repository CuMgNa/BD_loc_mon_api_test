# Windows 下运行 pytest（控制台 UTF-8）

`logger_util`、`conftest` 等会使用 emoji 美化日志。默认 GBK 编码的控制台在遇到这些字符时可能触发 **`UnicodeEncodeError`**。采用环境方式解决，无需改代码。

## 推荐（同时使用）

在当前终端会话中：

**PowerShell**

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
pytest
```

**cmd**

```bat
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
pytest
```

也可不用环境变量，直接：

```powershell
python -X utf8 -m pytest ...
```

## 可选

- 在 **cmd** 中先执行 `chcp 65001` 再跑 pytest。
- 使用 **Windows Terminal** / **PowerShell 7+**，并在 Cursor/VS Code 中将集成终端设为 UTF-8。

## CI

若在流水线中运行 pytest，在对应步骤的 `env` 中设置同上两个变量即可。
