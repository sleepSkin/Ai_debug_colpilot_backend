from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json

from .ollama_client import OllamaError
from .schemas import DebugRequest, DebugResponse, ParseRequest
from .services.debug_service import SchemaValidationError, run_debug, run_parse

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
    ???????

    Args:
        None.

    Returns:
        ??????? JSON?

    Raises:
        None.
    """
    return {"ok": True}


@app.post("/parse")
async def parse(req: ParseRequest) -> dict:
    """
    ?????????????????

    Args:
        req: ???????

    Returns:
        ????? JSON?

    Raises:
        HTTPException: ??????????????
    """
    try:
        obj, _raw = await run_parse(req)
        return obj
    except OllamaError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Model output is not valid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/debug", response_model=DebugResponse)
async def debug(req: DebugRequest):
    """
    ?????????????????

    Args:
        req: ???????

    Returns:
        DebugResponse ???

    Raises:
        HTTPException: ??????????????
    """
    try:
        obj, _raw = await run_debug(req)
        return DebugResponse(**obj)
    except OllamaError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Model output is not valid JSON: {e}")
    except SchemaValidationError as e:
        # ???????????????????????????
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
