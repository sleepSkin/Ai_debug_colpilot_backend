from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json

from .ollama_client import OllamaError
from .schemas import (
    DebugRequest,
    DebugResponse,
)
from .services.debug_service import SchemaValidationError, run_debug

app = FastAPI(title="AI Debug Copilot API", version="0.1.0")

# Allow local frontend calls during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """
    健康检查接口。

    Args:
        None.

    Returns:
        简单的健康状态 JSON。

    Raises:
        None.
    """
    return {"ok": True}


@app.post("/debug", response_model=DebugResponse)
async def debug(req: DebugRequest):
    """
    触发一次调试推理并返回结构化结果。

    Args:
        req: 调试请求参数。

    Returns:
        DebugResponse 结构。

    Raises:
        HTTPException: 当模型调用或解析失败时抛出。
    """
    try:
        obj, raw = await run_debug(req)
        return DebugResponse(**obj, raw_model_output=raw)
    except OllamaError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Model output is not valid JSON: {e}")
    except SchemaValidationError as e:
        # 这里选择 500：结构化校验失败属于后端推理链路问题，不是用户输入错误。
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
