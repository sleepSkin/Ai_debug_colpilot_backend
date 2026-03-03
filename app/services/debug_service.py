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
from ..prompt import DEBUG_PROMPT_TEMPLATE, PARSE_PROMPT_TEMPLATE
from ..schemas import DebugRequest, ParseRequest


logger = logging.getLogger(__name__)
ALLOWED_LANGS = {"ts", "js", "python", "unknown"}


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


def _to_str(value: Any) -> str:
    """
    将任意值转换为字符串；None 转为空字符串。
    """
    if value is None:
        return ""
    return str(value)


def _to_lang(value: Any) -> str:
    """
    将语言字段归一化到受限枚举。
    """
    lang = _to_str(value).strip().lower()
    if lang not in ALLOWED_LANGS:
        return "unknown"
    return lang


def _to_str_dict(value: Any) -> dict[str, str]:
    """
    将对象归一化为字符串字典。
    """
    if not isinstance(value, dict):
        return {}
    return {str(k): _to_str(v) for k, v in value.items()}


def _to_code_blocks(value: Any) -> list[dict[str, str]]:
    """
    将 code_blocks 归一化为 [{language, content}] 列表。
    """
    if not isinstance(value, list):
        return []

    out: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(
                {
                    "language": _to_lang(item.get("language", "unknown")),
                    "content": _to_str(item.get("content", "")),
                }
            )
        else:
            out.append({"language": "unknown", "content": _to_str(item)})
    return out


def _to_confidence(value: Any) -> float:
    """
    将置信度归一化到 0~1。
    """
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def _validate_parse_schema(obj: dict) -> dict:
    """
    校验 parse 输出必填字段并做类型归一化。
    """
    required = [
        "language_guess",
        "top_error_line",
        "error_text",
        "stack_trace_lines",
        "code_blocks",
        "logs",
        "file_paths",
        "environment_hints",
        "user_intent",
        "confidence",
    ]
    for key in required:
        if key not in obj:
            raise SchemaValidationError(f"Missing field: {key}")

    env = obj.get("environment_hints")
    if not isinstance(env, dict):
        env = {}

    return {
        "language_guess": _to_lang(obj.get("language_guess")),
        "top_error_line": _to_str(obj.get("top_error_line")),
        "error_text": _to_str(obj.get("error_text")),
        "stack_trace_lines": _list_to_str_list(obj.get("stack_trace_lines")),
        "code_blocks": _to_code_blocks(obj.get("code_blocks")),
        "logs": _list_to_str_list(obj.get("logs")),
        "file_paths": _list_to_str_list(obj.get("file_paths")),
        "environment_hints": {
            "os": _to_str(env.get("os")),
            "runtime": _to_str(env.get("runtime")),
            "framework": _to_str(env.get("framework")),
            "versions": _to_str_dict(env.get("versions")),
        },
        "user_intent": _to_str(obj.get("user_intent")),
        "confidence": _to_confidence(obj.get("confidence")),
    }


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


def _parse_json_output(raw: str, *, context: str) -> dict:
    """
    解析任意 JSON 输出（不做字段校验）。

    Args:
        raw: 模型原始输出文本。
        context: 解析上下文标识（用于日志定位）。

    Returns:
        解析后的 JSON 对象。

    Raises:
        json.JSONDecodeError: JSON 解析失败。
    """
    raw_stripped = _strip_code_fences(raw)
    try:
        return json.loads(raw_stripped)
    except json.JSONDecodeError:
        _log_raw_snippet(raw, f"{context}:json")
        raise


def _parse_parse_output(raw: str, *, context: str) -> dict:
    """
    解析并校验 /parse 输出。
    """
    obj = _parse_json_output(raw, context=context)
    try:
        return _validate_parse_schema(obj)
    except SchemaValidationError:
        _log_raw_snippet(raw, f"{context}:schema")
        raise


async def _run_llm_json(prompt: str) -> tuple[dict, str]:
    """
    调用 Ollama 并解析 JSON 输出，失败时重试一次（不做结构化校验）。

    Args:
        prompt: 发送给模型的提示词。

    Returns:
        (解析后的 JSON, 原始模型输出)。

    Raises:
        json.JSONDecodeError: JSON 解析失败。
        Exception: 调用模型失败或发生其他未知异常。
    """
    raw = await call_ollama(prompt)
    try:
        obj = _parse_parse_output(raw, context="parse:first")
        return obj, raw
    except (json.JSONDecodeError, SchemaValidationError):
        retry_prompt = (
            prompt
            + "\n\nYour output did not meet the required format. "
            "Please output JSON only and include fields "
            "language_guess/top_error_line/error_text/stack_trace_lines/"
            "code_blocks/logs/file_paths/environment_hints/user_intent/confidence."
        )
        raw_retry = await call_ollama(retry_prompt)
        obj_retry = _parse_parse_output(raw_retry, context="parse:retry")
        return obj_retry, raw_retry


async def run_parse(req: ParseRequest) -> tuple[dict, str]:
    """
    运行解析抽取流程，不做任何数据库写入。

    Args:
        req: 解析请求参数（包含 raw_input）。

    Returns:
        (结构化解析结果, 原始模型输出)。

    Raises:
        json.JSONDecodeError: JSON 解析失败。
        SchemaValidationError: parse 结构化校验失败。
        Exception: 调用模型失败或发生其他未知异常。
    """
    prompt = PARSE_PROMPT_TEMPLATE.format(raw_input=req.raw_input)
    obj, raw = await _run_llm_json(prompt)
    return obj, raw


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
    parsed = req.parsed or {}
    prompt = DEBUG_PROMPT_TEMPLATE.format(
        raw_input=req.raw_input,
        language_guess=parsed.get("language_guess", "unknown"),
        top_error_line=parsed.get("top_error_line", ""),
        error_text=parsed.get("error_text", ""),
        stack_trace_lines_json=json.dumps(parsed.get("stack_trace_lines", []), ensure_ascii=False),
        code_blocks_json=json.dumps(parsed.get("code_blocks", []), ensure_ascii=False),
        logs_json=json.dumps(parsed.get("logs", []), ensure_ascii=False),
        file_paths_json=json.dumps(parsed.get("file_paths", []), ensure_ascii=False),
        environment_hints_json=json.dumps(parsed.get("environment_hints", {}), ensure_ascii=False),
        user_intent=parsed.get("user_intent", ""),
        similar_bugs=req.similar_bugs or "",
    )
    obj, raw = await _run_llm(prompt)
    return obj, raw
