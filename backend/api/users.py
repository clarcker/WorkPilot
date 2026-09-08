"""
用户管理路由。

角色权限说明：
  super_admin  — 管理全部用户（除了不能创建另一个 super_admin）
  dept_admin   — 只能管理本部门的普通员工

GET    /api/admin/users                      列出用户（分页 + 过滤）
GET    /api/admin/users/suggest-username     建议用户名（拼音 + 去重）
GET    /api/admin/users/suggest-employee-no  建议员工编号（DEPT_CODE + 自增序号）
POST   /api/admin/users                      新建用户
GET    /api/admin/users/{id}                 用户详情
PATCH  /api/admin/users/{id}                 修改用户信息
POST   /api/admin/users/{id}/reset-password  重置密码（返回新随机密码）
PATCH  /api/admin/users/{id}/status          启用 / 禁用
POST   /api/admin/users/{id}/unlock          解锁账号
POST   /api/admin/users/{id}/force-logout    强制登出（仅 super_admin）
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import AuditAction, write_audit
from core.deps import require_admin, require_super_admin
from core.logger import logger
from core.security import generate_random_password, hash_password
from db.models import Department, User, UserRole
from db.session import get_db
from schemas.common import BaseResp, PagedData
from schemas.users import (
    ResetPasswordOut,
    SuggestEmployeeNoOut,
    SuggestUsernameOut,
    UserCreate,
    UserCreateOut,
    UserOut,
    UserStatusUpdate,
    UserUpdate,
)

router = APIRouter()


# ------------------------------------------------------------------
# 内部工具函数
# ------------------------------------------------------------------

def _get_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _user_to_out(user: User) -> UserOut:
    """ORM User → UserOut，需要 user.department 已加载（selectinload）。"""
    dept_name = user.department.dept_name if user.department else None
    dept_code = user.department.dept_code if user.department else None
    return UserOut(
        id=user.id,
        username=user.username,
        employee_no=user.employee_no,
        display_name=user.display_name,
        real_name=user.real_name,
        role=user.role.value,
        dept_id=user.dept_id,
        dept_name=dept_name,
        dept_code=dept_code,
        email=user.email,
        is_active=user.is_active,
        locked_at=user.locked_at,
        failed_login_count=user.failed_login_count,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        notes=user.notes,
    )


def _check_scope(actor: User, target: User) -> None:
    """
    dept_admin 只能操作本部门的普通员工。
    super_admin 调用时直接返回（无限制）。
    """
    if actor.role == UserRole.super_admin:
        return
    # dept_admin 不能动 super_admin / dept_admin
    if target.role in (UserRole.super_admin, UserRole.dept_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40301, "message": "无权操作该角色的用户"},
        )
    # dept_admin 只能操作本部门
    if target.dept_id != actor.dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40301, "message": "无权操作其他部门的用户"},
        )


async def _load_user(db: AsyncSession, user_id: int) -> User:
    """按 id 加载用户（含部门关联），不存在则 404。"""
    user = await db.scalar(
        select(User)
        .options(selectinload(User.department))
        .where(User.id == user_id)
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 40400, "message": "用户不存在"},
        )
    return user


# ------------------------------------------------------------------
# GET /   列出用户（分页 + 过滤）
# ------------------------------------------------------------------

@router.get("/", response_model=BaseResp[PagedData[UserOut]])
async def list_users(
    page:      int        = Query(default=1,    ge=1),
    page_size: int        = Query(default=20,   ge=1, le=100),
    dept_id:   int | None = Query(default=None, description="按部门过滤（仅 super_admin 可用）"),
    role:      str | None = Query(default=None, description="按角色过滤"),
    keyword:   str | None = Query(default=None, max_length=100, description="搜索姓名/用户名/员工编号"),
    is_active: bool | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    conditions = []

    if current_user.role == UserRole.dept_admin:
        # dept_admin：只看自己部门的普通员工
        conditions.append(User.dept_id == current_user.dept_id)
        conditions.append(User.role == UserRole.employee)
    else:
        # super_admin：可按部门/角色过滤
        if dept_id is not None:
            conditions.append(User.dept_id == dept_id)
        if role is not None:
            try:
                conditions.append(User.role == UserRole(role))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": 42200, "message": f"无效角色值: {role}"},
                )

    if keyword:
        conditions.append(
            or_(
                User.real_name.ilike(f"%{keyword}%"),
                User.username.ilike(f"%{keyword}%"),
                User.employee_no.ilike(f"%{keyword}%"),
            )
        )

    if is_active is not None:
        conditions.append(User.is_active == is_active)

    # 总数
    count_stmt = select(func.count(User.id))
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
    total = await db.scalar(count_stmt) or 0

    # 数据
    data_stmt = (
        select(User)
        .options(selectinload(User.department))
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    for cond in conditions:
        data_stmt = data_stmt.where(cond)
    rows = await db.execute(data_stmt)
    users = rows.scalars().all()

    return BaseResp.ok(
        PagedData(
            items=[_user_to_out(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


# ------------------------------------------------------------------
# GET /suggest-username
# ------------------------------------------------------------------

@router.get("/suggest-username", response_model=BaseResp[SuggestUsernameOut])
async def suggest_username(
    name: str = Query(..., min_length=1, max_length=50, description="真实姓名（中文或英文）"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    根据真实姓名生成建议用户名。
    中文 → 全拼小写（zhangsan）；重名时加序号（zhangsan01）。
    """
    from pypinyin import lazy_pinyin, Style

    # 全拼，无声调，连接
    pinyin_base = "".join(lazy_pinyin(name, style=Style.NORMAL)).lower()
    # 只保留小写字母（过滤掉数字、空格、特殊字符）
    pinyin_base = "".join(c for c in pinyin_base if c.isalpha())

    if not pinyin_base:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": 42200, "message": "无法从姓名生成有效拼音，请检查姓名内容"},
        )

    # 找第一个不冲突的候选名
    candidate = pinyin_base
    suffix = 0
    while True:
        taken = await db.scalar(select(User.id).where(User.username == candidate))
        if not taken:
            break
        suffix += 1
        candidate = f"{pinyin_base}{suffix:02d}"

    return BaseResp.ok(
        SuggestUsernameOut(suggested=candidate, pinyin_base=pinyin_base)
    )


# ------------------------------------------------------------------
# GET /suggest-employee-no
# ------------------------------------------------------------------

@router.get("/suggest-employee-no", response_model=BaseResp[SuggestEmployeeNoOut])
async def suggest_employee_no(
    dept_id: int = Query(..., description="目标部门 ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    建议下一个可用员工编号。
    规则：dept_code + 3 位自增序号，如 HR001、RD023。
    """
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 40400, "message": "部门不存在"},
        )

    prefix = dept.dept_code  # 如 "HR"

    # 查该部门所有以 prefix 开头的员工编号
    rows = await db.execute(
        select(User.employee_no)
        .where(User.dept_id == dept_id)
        .where(User.employee_no.like(f"{prefix}%"))
    )
    existing = [r[0] for r in rows]

    max_seq = 0
    for no in existing:
        suffix = no[len(prefix):]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))

    next_seq = max_seq + 1
    suggested = f"{prefix}{next_seq:03d}"

    return BaseResp.ok(
        SuggestEmployeeNoOut(suggested=suggested, dept_code=prefix, next_seq=next_seq)
    )


# ------------------------------------------------------------------
# POST /   创建用户
# ------------------------------------------------------------------

@router.post("/", response_model=BaseResp[UserCreateOut], status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreate,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # ---- 角色合法性 ----
    try:
        new_role = UserRole(req.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": 42200, "message": f"无效角色值: {req.role}，可选 employee / dept_admin"},
        )

    if new_role == UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40300, "message": "不允许通过此接口创建超级管理员账号"},
        )

    # dept_admin 只能创建本部门普通员工
    if current_user.role == UserRole.dept_admin:
        if new_role != UserRole.employee:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "message": "部门管理员只能创建普通员工"},
            )
        # 强制归属到操作者的部门
        if req.dept_id is not None and req.dept_id != current_user.dept_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "message": "只能在本部门创建用户"},
            )
        req.dept_id = current_user.dept_id

    # ---- 部门存在性 ----
    if req.dept_id is not None:
        if not await db.get(Department, req.dept_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": 40400, "message": "指定部门不存在"},
            )

    # ---- 用户名唯一 ----
    if await db.scalar(select(User.id).where(User.username == req.username)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": 40900, "message": f"用户名 {req.username!r} 已存在"},
        )

    # ---- 员工编号唯一 ----
    if await db.scalar(select(User.id).where(User.employee_no == req.employee_no)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": 40900, "message": f"员工编号 {req.employee_no!r} 已存在"},
        )

    # ---- 生成初始随机密码 ----
    init_pwd = generate_random_password()

    user = User(
        username=req.username,
        employee_no=req.employee_no,
        real_name=req.real_name,
        display_name=req.real_name,   # 默认昵称 = 真实姓名
        dept_id=req.dept_id,
        role=new_role,
        email=req.email,
        notes=req.notes,
        password_hash=hash_password(init_pwd),
        must_change_password=True,
        created_by=current_user.id,
    )
    db.add(user)
    await db.flush()

    # 加载部门关联信息（用于响应）
    await db.refresh(user, attribute_names=["department"])

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.USER_CREATE,
        resource_type="user",
        resource_id=str(user.id),
        new_value={
            "username": user.username,
            "employee_no": user.employee_no,
            "real_name": user.real_name,
            "role": user.role.value,
            "dept_id": user.dept_id,
        },
        ip_address=_get_ip(request),
    )

    logger.info("User created | username={username} | by={operator}", username=user.username, operator=current_user.username)

    base = _user_to_out(user)
    return BaseResp.ok(
        UserCreateOut(**base.model_dump(), init_password=init_pwd)
    )


# ------------------------------------------------------------------
# GET /{user_id}   用户详情
# ------------------------------------------------------------------

@router.get("/{user_id}", response_model=BaseResp[UserOut])
async def get_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await _load_user(db, user_id)
    _check_scope(current_user, target)
    return BaseResp.ok(_user_to_out(target))


# ------------------------------------------------------------------
# PATCH /{user_id}   修改用户信息
# ------------------------------------------------------------------

@router.patch("/{user_id}", response_model=BaseResp[UserOut])
async def update_user(
    user_id: int,
    req: UserUpdate,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await _load_user(db, user_id)
    _check_scope(current_user, target)

    # 不允许修改自己的角色（防止锁死）
    if user_id == current_user.id and req.role is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40300, "message": "不允许修改自己的角色"},
        )

    old_snapshot = {
        "display_name": target.display_name,
        "email": target.email,
        "dept_id": target.dept_id,
        "role": target.role.value,
        "notes": target.notes,
    }

    # dept_admin 只能改 display_name / email / notes
    if current_user.role == UserRole.dept_admin:
        if req.dept_id is not None or req.role is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "message": "部门管理员无权修改用户的部门或角色"},
            )

    # 应用字段
    if req.display_name is not None:
        target.display_name = req.display_name
    if req.email is not None:
        target.email = req.email
    if req.notes is not None:
        target.notes = req.notes

    # 以下仅 super_admin 可改（dept_admin 在上面已拦截）
    if req.dept_id is not None:
        if not await db.get(Department, req.dept_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": 40400, "message": "指定部门不存在"},
            )
        target.dept_id = req.dept_id

    if req.role is not None:
        try:
            new_role = UserRole(req.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": 42200, "message": f"无效角色值: {req.role}"},
            )
        if new_role == UserRole.super_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": 40300, "message": "不允许将用户提升为超级管理员"},
            )
        target.role = new_role

    new_snapshot = {
        "display_name": target.display_name,
        "email": target.email,
        "dept_id": target.dept_id,
        "role": target.role.value,
        "notes": target.notes,
    }

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.USER_UPDATE,
        resource_type="user",
        resource_id=str(target.id),
        old_value=old_snapshot,
        new_value=new_snapshot,
        ip_address=_get_ip(request),
    )

    # 重新加载部门（dept_id 可能变了）
    await db.refresh(target, attribute_names=["department"])
    logger.info("User updated | user_id={user_id} | by={operator}", user_id=target.id, operator=current_user.username)
    return BaseResp.ok(_user_to_out(target))


# ------------------------------------------------------------------
# POST /{user_id}/reset-password   重置密码
# ------------------------------------------------------------------

@router.post("/{user_id}/reset-password", response_model=BaseResp[ResetPasswordOut])
async def reset_password(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await _load_user(db, user_id)
    _check_scope(current_user, target)

    # 不允许重置自己的密码（用改密接口）
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40300, "message": "请使用「修改密码」接口修改自己的密码"},
        )

    new_pwd = generate_random_password()
    target.password_hash = hash_password(new_pwd)
    target.must_change_password = True

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.USER_RESET_PWD,
        resource_type="user",
        resource_id=str(target.id),
        ip_address=_get_ip(request),
    )

    logger.info("Password reset | user_id={user_id} | by={operator}", user_id=target.id, operator=current_user.username)

    return BaseResp.ok(ResetPasswordOut(new_password=new_pwd, must_change_password=True))


# ------------------------------------------------------------------
# PATCH /{user_id}/status   启用 / 禁用
# ------------------------------------------------------------------

@router.patch("/{user_id}/status", response_model=BaseResp[None])
async def update_user_status(
    user_id: int,
    req: UserStatusUpdate,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await _load_user(db, user_id)
    _check_scope(current_user, target)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40300, "message": "不允许禁用自己的账号"},
        )

    if target.is_active == req.is_active:
        action_str = "启用" if req.is_active else "禁用"
        return BaseResp.ok(message=f"账号已是{action_str}状态，无需操作")

    target.is_active = req.is_active
    action = AuditAction.USER_ENABLE if req.is_active else AuditAction.USER_DISABLE

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=action,
        resource_type="user",
        resource_id=str(target.id),
        ip_address=_get_ip(request),
    )

    msg = "账号已启用" if req.is_active else "账号已禁用"
    logger.info("User status changed | user_id={user_id} | active={active} | by={operator}", user_id=target.id, active=req.is_active, operator=current_user.username)
    return BaseResp.ok(message=msg)


# ------------------------------------------------------------------
# POST /{user_id}/unlock   解锁账号
# ------------------------------------------------------------------

@router.post("/{user_id}/unlock", response_model=BaseResp[None])
async def unlock_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await _load_user(db, user_id)
    _check_scope(current_user, target)

    if not target.locked_at:
        return BaseResp.ok(message="账号未处于锁定状态")

    target.locked_at = None
    target.failed_login_count = 0

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.USER_UNLOCK,
        resource_type="user",
        resource_id=str(target.id),
        ip_address=_get_ip(request),
    )

    logger.info("User unlocked | user_id={user_id} | by={operator}", user_id=target.id, operator=current_user.username)

    return BaseResp.ok(message="账号已解锁")


# ------------------------------------------------------------------
# POST /{user_id}/force-logout   强制登出（仅 super_admin）
# ------------------------------------------------------------------

@router.post("/{user_id}/force-logout", response_model=BaseResp[None])
async def force_logout(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_super_admin),   # 仅超级管理员
    db: AsyncSession = Depends(get_db),
):
    target = await _load_user(db, user_id)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40300, "message": "不允许对自己执行强制登出"},
        )

    # 将该时间之前签发的所有 Token 都标记为无效
    target.tokens_invalidated_before = datetime.now(timezone.utc)

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.USER_FORCE_LOGOUT,
        resource_type="user",
        resource_id=str(target.id),
        ip_address=_get_ip(request),
    )

    logger.info("User force logout | user_id={user_id} | by={operator}", user_id=target.id, operator=current_user.username)

    return BaseResp.ok(message=f"已强制登出用户 {target.real_name}（{target.username}）")
