from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ToolContext:
    user_id: int
    user_role: str
    user_dept_id: Optional[int] = None
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None
    # 演练模式：工具照常做权限/参数校验并返回结构化结果，但不产生外部副作用
    # （不写库、不发通知）。评测回归用，避免每跑一次 eval 就建一批真工单。
    dry_run: bool = False


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    deny_reason: Optional[str] = None


@dataclass
class ToolDef:
    name: str
    description: str
    func: Callable
    permissions: list[str] = field(default_factory=list)
    params_schema: dict = field(default_factory=dict)
    is_idempotent: bool = False


def _build_params_schema(func: Callable) -> dict:
    """
    从函数签名推断 JSON Schema。

    注意：工具的实际签名是 (args: dict, ctx: ToolContext)，两个形参都会被跳过，
    因此这里几乎总是返回空 schema。真实参数请在 @tool(parameters=...) 中显式声明，
    否则 decide_tool 节点拼出的提示词里不会包含任何参数名，LLM 只能自己编
    （历史 bug：模型生成了 {"问题类型": ...} 而工具读的是 args["issue_type"]）。
    """
    sig = inspect.signature(func)
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name in ("args", "ctx"):
            continue
        annotation = param.annotation
        json_type = type_map.get(annotation, "string")
        prop: dict[str, Any] = {"type": json_type}
        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(name)
        properties[name] = prop

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef) -> None:
        if tool_def.name in self._tools:
            raise ValueError(f"Tool '{tool_def.name}' is already registered")
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def get_tools_for_prompt(self, role: str) -> list[dict]:
        result: list[dict] = []
        for td in self._tools.values():
            if td.permissions and role not in td.permissions:
                continue
            result.append(
                {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.params_schema,
                }
            )
        return result

    async def execute(self, name: str, args: dict, ctx: ToolContext) -> ToolResult:
        td = self.get(name)
        if td is None:
            return ToolResult(success=False, error=f"Tool '{name}' not found")

        if td.permissions and ctx.user_role not in td.permissions:
            return ToolResult(
                success=False,
                deny_reason=f"Role '{ctx.user_role}' is not allowed to use tool '{name}'",
            )

        required = td.params_schema.get("required", [])
        for param_name in required:
            if param_name not in args:
                return ToolResult(
                    success=False, error=f"Missing required parameter: {param_name}"
                )

        coerced_args = dict(args)
        for param_name, prop in td.params_schema.get("properties", {}).items():
            if param_name in coerced_args and prop.get("type") == "integer":
                try:
                    coerced_args[param_name] = int(coerced_args[param_name])
                except (ValueError, TypeError):
                    pass

        try:
            result = await td.func(coerced_args, ctx)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(success=True, data=result)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


def make_idempotency_key(user_id: int, **kwargs: Any) -> str:
    parts = [f"user_id={user_id}"]
    for k in sorted(kwargs):
        parts.append(f"{k}={kwargs[k]}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


tool_registry = ToolRegistry()


def tool(
    name: str,
    description: str,
    permissions: list[str] | None = None,
    is_idempotent: bool = False,
    parameters: dict | None = None,
) -> Callable:
    """
    注册一个工具。

    Args:
        parameters: 显式 JSON Schema（{"type": "object", "properties": {...},
            "required": [...]}）。务必声明——工具签名统一是 (args, ctx)，
            无法从签名推断出真实参数。省略时回退到签名推断（通常为空）。
    """
    def decorator(func: Callable) -> Callable:
        params_schema = parameters if parameters is not None else _build_params_schema(func)
        td = ToolDef(
            name=name,
            description=description,
            func=func,
            permissions=permissions or [],
            params_schema=params_schema,
            is_idempotent=is_idempotent,
        )
        tool_registry.register(td)
        func._tool_def = td  # type: ignore[attr-defined]
        return func

    return decorator
