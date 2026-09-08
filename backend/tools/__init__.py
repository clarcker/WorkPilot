"""工具注册。导入所有工具模块使 @tool 装饰器执行注册。"""
from tools.base import tool_registry
import tools.employee       # noqa: F401
import tools.reimbursement  # noqa: F401
import tools.ticket         # noqa: F401
__all__ = ["tool_registry"]