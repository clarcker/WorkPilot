"""
数据库相关的测试辅助函数
"""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, Department
from core.security import hash_password


async def create_user(
    db_session: AsyncSession,
    username: str,
    password: str = "Password@123",
    real_name: str = "测试用户",
    role: str = "employee",
    dept_id: int = None,
    is_active: bool = True,
    **kwargs
) -> User:
    """创建测试用户"""
    user = User(
        username=username,
        password_hash=hash_password(password),
        real_name=real_name,
        display_name=kwargs.get("display_name", real_name),
        employee_no=kwargs.get("employee_no", f"EMP{abs(hash(username))%10000:04d}"),
        role=role,
        dept_id=dept_id,
        is_active=is_active,
        must_change_password=kwargs.get("must_change_password", False),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_department(
    db_session: AsyncSession,
    dept_code: str,
    dept_name: str,
) -> Department:
    """创建测试部门"""
    dept = Department(dept_code=dept_code, dept_name=dept_name)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


async def lock_user_account(
    db_session: AsyncSession,
    user: User,
    fail_count: int = 5,
) -> None:
    """锁定用户账户"""
    user.failed_login_count = fail_count
    user.locked_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(user)


async def disable_user(db_session: AsyncSession, user: User) -> None:
    """禁用用户"""
    user.is_active = False
    await db_session.commit()
    await db_session.refresh(user)


async def enable_user(db_session: AsyncSession, user: User) -> None:
    """启用用户"""
    user.is_active = True
    user.locked_at = None
    user.failed_login_count = 0
    await db_session.commit()
    await db_session.refresh(user)


async def set_must_change_password(
    db_session: AsyncSession,
    user: User,
    must_change: bool = True,
) -> None:
    """设置用户必须修改密码标志"""
    user.must_change_password = must_change
    await db_session.commit()
    await db_session.refresh(user)
