"""
本文件实现纯推理服务的调试流程，不做任何数据库读写。

设计说明：
- 后端仅负责构造 prompt、调用 Ollama、解析和校验 JSON。
- 数据持久化由 Next.js/Node 层负责，避免 Python 端连接数据库。
- 如需扩展（RAG、相似 bug 检索），建议在 Next.js 或独立服务实现。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..ollama_client import call_ollama
from ..prompt import PROMPT_TEMPLATE
from ..schemas import DebugRequest


logger = logging.getLogger(__name__)


class SchemaValidationError(ValueError):
    """
    模型输出结构化校验失败时抛出的错误类型。

    Args:
        message: 详细错误信息。

    Returns:
        None.

    Raises:
        ValueError: 当模型输出缺少必填字段或字段类型不合规时抛出。
    """


def _strip_code_fences(text: str) -> str:
    """
    去除模型输出外层的 Markdown 代码块标记。

    Args:
        text: 原始模型输出文本。

    Returns:
        去除代码块标记后的字符串。

    Raises:
        None.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _list_to_str_list(value: Any) -> list[str]:
    """
    将模型输出归一化为字符串列表。

    Args:
        value: 模型输出中的任意字段值。

    Returns:
        归一化后的字符串数组。

    Raises:
        None.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return [str(value)]

    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            # 若是字典，优先提取常见字段，否则保存为 JSON 字符串。
            for key in ("cause", "suggestion", "advice"):
                if key in item and isinstance(item[key], str):
                    out.append(item[key])
                    break
            else:
                out.append(json.dumps(item, ensure_ascii=False))
        else:
            out.append(str(item))
    return out


def _validate_schema(obj: dict) -> dict:
    """
    校验模型输出是否包含必须字段并进行类型归一化。

    Args:
        obj: 解析后的 JSON 对象。

    Returns:
        校验并归一化后的对象。

    Raises:
        SchemaValidationError: 当缺少必填字段或字段类型不符合预期时抛出。
    """
    required = ["error_type", "root_cause", "fix_suggestions", "prevention"]
    for key in required:
        if key not in obj:
            raise SchemaValidationError(f"Missing field: {key}")

    obj["error_type"] = str(obj["error_type"])
    obj["root_cause"] = _list_to_str_list(obj["root_cause"])
    obj["fix_suggestions"] = _list_to_str_list(obj["fix_suggestions"])
    obj["prevention"] = _list_to_str_list(obj["prevention"])
    return obj


def _log_raw_snippet(raw: str, reason: str) -> None:
    """
    记录模型原始输出的片段，避免日志过长。

    Args:
        raw: 模型原始输出文本。
        reason: 记录原因标识。

    Returns:
        None.

    Raises:
        None.
    """
    snippet = raw[:800]
    logger.warning("模型输出解析失败，原因=%s，raw_snippet=%s", reason, snippet)


def _parse_model_output(raw: str, *, context: str) -> dict:
    """
    解析并校验模型输出。

    Args:
        raw: 模型原始输出文本。
        context: 解析上下文标识（用于日志定位）。

    Returns:
        校验后的结构化对象。

    Raises:
        json.JSONDecodeError: JSON 解析失败。
        SchemaValidationError: 结构化校验失败。
    """
    raw_stripped = _strip_code_fences(raw)
    try:
        obj = json.loads(raw_stripped)
    except json.JSONDecodeError:
        _log_raw_snippet(raw, f"{context}:json")
        raise

    try:
        return _validate_schema(obj)
    except SchemaValidationError:
        _log_raw_snippet(raw, f"{context}:schema")
        raise


async def _run_llm(prompt: str) -> tuple[dict, str]:
    """
    调用 Ollama 并解析输出，失败时重试一次。

    Args:
        prompt: 发送给模型的提示词。

    Returns:
        (结构化结果, 原始模型输出)。

    Raises:
        json.JSONDecodeError: JSON 解析失败。
        SchemaValidationError: 结构化校验失败。
        Exception: 调用模型失败或发生其他未知异常。
    """
    raw = await call_ollama(prompt)
    try:
        obj = _parse_model_output(raw, context="first")
        return obj, raw
    except (json.JSONDecodeError, SchemaValidationError):
        retry_prompt = (
            prompt
            + "\n\nYour output did not meet the required format. "
            "Please output JSON only and include fields "
            "error_type/root_cause/fix_suggestions/prevention."
        )
        raw_retry = await call_ollama(retry_prompt)
        obj_retry = _parse_model_output(raw_retry, context="retry")
        return obj_retry, raw_retry


async def run_debug(req: DebugRequest) -> tuple[dict, str]:
    """
    运行调试推理流程，不做任何数据库写入。

    Args:
        req: 调试请求参数（包含 language/errorText/codeSnippet/session_id）。

    Returns:
        (结构化结果, 原始模型输出)。

    Raises:
        json.JSONDecodeError: JSON 解析失败。
        SchemaValidationError: 结构化校验失败。
        Exception: 调用模型失败或发生其他未知异常。
    """
    prompt = PROMPT_TEMPLATE.format(
        language=req.language,
        similar_bugs="(none yet)",
        error_text=req.errorText,
        code_snippet=req.codeSnippet or "(not provided)",
    )
    obj, raw = await _run_llm(prompt)
    return obj, raw
