记得先启动ollama
ollama list/ollama serve


先开虚拟环境
venv\Scripts\activate

设置ollama参数
$env:OLLAMA_MODEL="qwen2.5:7b-instruct"
$env:OLLAMA_MODE="generate"

开启后端uvicorn服务
uvicorn app.main:app --port 8000
uvicorn app.main:app --host 0.0.0.0 --port 8000  // docker对应的

测试debug接口
 curl.exe -X POST "http://localhost:8000/debug" -H "Content-Type: application/json" --data-binary "@debug_req.json"

Codex Prompt 片段（通用可复用）
    验收标准（必须满足，否则你需要继续修改直到满足）：
    新增/修改的每个函数都有 docstring（Args/Returns/Raises）
    每个事务边界都有注释（为什么在这里 begin/commit/rollback）
    所有异常处理分支都有注释说明意图
    输出前请自检并列出“自检清单（pass/fail）”