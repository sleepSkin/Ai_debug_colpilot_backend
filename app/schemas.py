"""
本文件负责定义所有 Pydantic Schema，统一 API 输入/输出的数据结构与注释。
调用关系：main.py（路由层） -> schemas.py（数据校验/序列化） -> service/db（业务与持久化）。

命名与兼容策略说明：
- 对外响应统一使用 snake_case，便于 API 一致性与后端维护。
- 通过 Pydantic 的 validation_alias 兼容历史 camelCase 输入/内部 dict。
- 这样既不破坏现有调用，又能让输出风格一致。

用法示例（说明 alias 如何兼容）：
- 内部 dict（camelCase）也可被解析：
  {"createdAt": "2026-01-01T00:00:00Z", "messageCount": 2}
- 对外序列化（snake_case）仍保持：
  {"created_at": "2026-01-01T00:00:00Z", "message_count": 2}
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class _BaseSchema(BaseModel):
    """
    所有 Schema 的基类。

    设计决策：
    - 开启 populate_by_name，让字段名与 alias 都可被解析。
    - 仅使用 validation_alias 来兼容旧字段，序列化仍走字段名（snake_case）。
    """

    model_config = ConfigDict(populate_by_name=True)


class ParseRequest(_BaseSchema):
    """
    /parse 请求体 Schema。

    用途：
    - 接收原始用户输入并触发解析抽取。
    """

    raw_input: str = Field(
        min_length=1,
        description="用户粘贴的原始输入文本。",
    )


class DebugRequest(_BaseSchema):
    """
    /debug 请求体 Schema。

    用途：
    - 接收 parse 阶段后的结构化信息并触发调试推理。
    """

    raw_input: str = Field(
        min_length=1,
        description="用户粘贴的原始输入文本（用于补充信息）。",
    )
    parsed: Dict[str, Any] = Field(
        description="Parse 阶段输出的结构化 JSON。",
    )
    similar_bugs: Optional[str] = Field(
        default=None,
        description="可选的相似历史错误文本。",
    )


class DebugResponse(_BaseSchema):
    """
    /debug 响应体 Schema（必须保持兼容）。

    用途：
    - 返回模型的结构化调试结果。

    字段设计决策：
    - 对外严格保持 snake_case，避免破坏现有前端解析。

    与其他 Schema 关系：
    - 与 DebugResultOut 的结构一致，但 DebugResultOut 用于历史查询场景。
    """

    error_type: str = Field(
        description="错误类型（模型判断）。示例：'TypeError'。",
    )
    root_cause: List[str] = Field(
        description="根因列表（字符串数组）。示例：['变量未定义']。",
    )
    fix_suggestions: List[str] = Field(
        description="修复建议列表（字符串数组）。示例：['检查参数类型']。",
    )
    prevention: List[str] = Field(
        description="预防建议列表（字符串数组）。示例：['增加类型检查']。",
    )


class SessionSummary(_BaseSchema):
    """
    /sessions 列表中的单条会话概要。

    用途：
    - 提供最近会话的基础信息和统计数据。

    字段设计决策：
    - 对外统一 snake_case。
    - 通过 validation_alias 兼容 service 层现有 camelCase dict。

    与其他 Schema 关系：
    - SessionListResponse.sessions 的元素。
    """

    id: str = Field(
        description="会话唯一 ID。",
    )
    created_at: datetime = Field(
        validation_alias=AliasChoices("createdAt", "created_at"),
        description="会话创建时间（UTC）。",
    )
    last_message_at: Optional[datetime] = Field(
        validation_alias=AliasChoices("lastMessageAt", "last_message_at"),
        description="最后一条消息时间；无消息时为 null。",
    )
    message_count: int = Field(
        validation_alias=AliasChoices("messageCount", "message_count"),
        description="当前会话的消息数量。",
    )


class SessionListResponse(_BaseSchema):
    """
    /sessions 响应体。

    用途：
    - 返回会话概要列表。

    字段设计决策：
    - sessions 为数组，外层结构稳定，便于扩展分页信息。

    与其他 Schema 关系：
    - items 使用 SessionSummary。
    """

    sessions: List[SessionSummary] = Field(
        description="会话概要列表。",
    )


class DebugResultOut(_BaseSchema):
    """
    /sessions/{session_id} 中 assistant 消息的结构化结果。

    用途：
    - 提供历史调试的结构化结果和元数据。

    字段设计决策：
    - root_cause/fix_suggestions/prevention 收窄为 List[str]，
      因为模型输出已被统一成字符串数组，便于前端渲染。
    - raw_model_output 保留原始文本，便于排查模型输出问题。

    与其他 Schema 关系：
    - MessageOut.debug_result 的内容。
    """

    error_type: str = Field(
        validation_alias=AliasChoices("errorType", "error_type"),
        description="错误类型（结构化结果）。",
    )
    root_cause: List[str] = Field(
        validation_alias=AliasChoices("rootCause", "root_cause"),
        description="根因列表（字符串数组）。",
    )
    fix_suggestions: List[str] = Field(
        validation_alias=AliasChoices("fixSuggestions", "fix_suggestions"),
        description="修复建议列表（字符串数组）。",
    )
    prevention: List[str] = Field(
        validation_alias=AliasChoices("prevention", "prevention"),
        description="预防建议列表（字符串数组）。",
    )
    raw_model_output: str = Field(
        validation_alias=AliasChoices("rawModelOutput", "raw_model_output"),
        description="模型原始输出文本。",
    )
    model_name: str = Field(
        validation_alias=AliasChoices("modelName", "model_name"),
        description="模型名称。示例：'qwen2.5:7b-instruct'。",
    )
    prompt_version: str = Field(
        validation_alias=AliasChoices("promptVersion", "prompt_version"),
        description="提示词版本号。示例：'v1'。",
    )
    created_at: datetime = Field(
        validation_alias=AliasChoices("createdAt", "created_at"),
        description="结果生成时间（UTC）。",
    )


class MessageOut(_BaseSchema):
    """
    /sessions/{session_id} 中的消息结构。

    用途：
    - 统一返回 user/assistant 两类消息。

    字段设计决策：
    - 使用 Optional 字段表示角色差异，并在注释中明确何时出现。
    - assistant_json 允许 dict[str, Any]，因为结构化内容可变。

    与其他 Schema 关系：
    - debug_result 仅在 role=assistant 时存在。
    """

    id: str = Field(
        description="消息唯一 ID。",
    )
    role: Literal["user", "assistant"] = Field(
        description="消息角色。user 表示用户输入，assistant 表示模型输出。",
    )
    language: Optional[str] = Field(
        default=None,
        description="仅 role=user 时有值：语言类型。assistant 消息为 null。",
    )
    error_text: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("errorText", "error_text"),
        description="仅 role=user 时有值：错误文本。assistant 消息为 null。",
    )
    code_snippet: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("codeSnippet", "code_snippet"),
        description="仅 role=user 时有值：代码片段。assistant 消息为 null。",
    )
    assistant_json: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("assistantJson", "assistant_json"),
        description=(
            "仅 role=assistant 时有值：结构化结果 JSON。"
            " 可能包含数组或复杂嵌套对象，因此使用 dict[str, Any]。"
        ),
    )
    raw_model_output: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("rawModelOutput", "raw_model_output"),
        description="仅 role=assistant 时有值：模型原始输出文本。",
    )
    created_at: datetime = Field(
        validation_alias=AliasChoices("createdAt", "created_at"),
        description="消息创建时间（UTC）。",
    )
    debug_result: Optional[DebugResultOut] = Field(
        default=None,
        validation_alias=AliasChoices("debugResult", "debug_result"),
        description="仅 role=assistant 时可能有值：结构化调试结果。",
    )


class SessionDetailResponse(_BaseSchema):
    """
    /sessions/{session_id} 响应体。

    用途：
    - 返回指定 session 的消息列表与元信息。

    字段设计决策：
    - 对外统一 snake_case；对内兼容 camelCase。

    与其他 Schema 关系：
    - messages 使用 MessageOut。
    """

    id: str = Field(
        description="会话唯一 ID。",
    )
    created_at: datetime = Field(
        validation_alias=AliasChoices("createdAt", "created_at"),
        description="会话创建时间（UTC）。",
    )
    updated_at: datetime = Field(
        validation_alias=AliasChoices("updatedAt", "updated_at"),
        description="会话最后更新时间（UTC），用于排序。",
    )
    messages: List[MessageOut] = Field(
        description="消息列表，按时间升序排列。",
    )
