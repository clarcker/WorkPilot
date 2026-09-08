"""
审计日志写入封装。

所有业务操作在完成后调用 write_audit()，
与主操作共享同一 db session，事务一起提交。

失败路径（如登录失败需要记录）需要传入独立 session 并手动 commit。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    operator_id: int | None,
    operator_name: str,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    ip_address: str | None = None,
    result: str = "success",
    detail: str | None = None,
) -> None:
    """
    追加一条审计日志到当前 session，不自动 commit。
    由 get_db 依赖在请求结束时统一提交。

    示例：
        await write_audit(
            db,
            operator_id=current_user.id,
            operator_name=current_user.real_name,
            action="doc.upload",
            resource_type="document",
            resource_id=str(doc.id),
            new_value={"file_name": doc.file_name},
            ip_address=request.client.host,
        )
    """
    log = AuditLog(
        operator_id=operator_id,
        operator_name=operator_name,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        result=result,
        detail=detail,
    )
    db.add(log)


# ------------------------------------------------------------------
# 便捷常量：action 枚举，与 API 接口清单保持一致
# ------------------------------------------------------------------
class AuditAction:
    # 认证
    AUTH_LOGIN          = "auth.login"
    AUTH_LOGOUT         = "auth.logout"
    AUTH_CHANGE_PWD     = "auth.change_password"

    # 用户管理
    USER_CREATE         = "user.create"
    USER_UPDATE         = "user.update"
    USER_RESET_PWD      = "user.reset_password"
    USER_DISABLE        = "user.disable"
    USER_ENABLE         = "user.enable"
    USER_UNLOCK         = "user.unlock"
    USER_FORCE_LOGOUT   = "user.force_logout"

    # 部门管理
    DEPT_CREATE         = "dept.create"
    DEPT_UPDATE         = "dept.update"
    DEPT_DELETE         = "dept.delete"

    # 文档管理
    DOC_UPLOAD          = "doc.upload"
    DOC_UPDATE          = "doc.update"
    DOC_ARCHIVE         = "doc.archive"
    DOC_DELETE          = "doc.delete"
    DOC_PERM_UPDATE     = "doc.permission_update"

    # 系统配置
    SYSTEM_CONFIG       = "system.config_update"

    # 工具调用
    TOOL_CALL          = "tool.call"
    TOOL_DENY          = "tool.deny"
