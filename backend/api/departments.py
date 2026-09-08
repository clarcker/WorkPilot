"""
部门管理路由（仅超级管理员）。

GET    /api/admin/departments          列出所有部门（含用户数）
POST   /api/admin/departments          新建部门
PATCH  /api/admin/departments/{id}    修改部门名称
DELETE /api/admin/departments/{id}    删除部门（需无关联用户）
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import AuditAction, write_audit
from core.deps import require_super_admin
from core.logger import logger
from db.models import Department, Document, User
from db.session import get_db
from schemas.common import BaseResp
from schemas.departments import DeptCreate, DeptOut, DeptUpdate

router = APIRouter()


def _get_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ------------------------------------------------------------------
# GET /
# ------------------------------------------------------------------

@router.get("/", response_model=BaseResp[list[DeptOut]])
async def list_departments(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出所有部门，附带每部门用户数。"""
    rows = await db.execute(
        select(
            Department.id,
            Department.dept_code,
            Department.dept_name,
            Department.created_at,
            func.count(User.id).label("user_count"),
        )
        .outerjoin(User, User.dept_id == Department.id)
        .group_by(Department.id)
        .order_by(Department.dept_code)
    )
    result = [
        DeptOut(
            id=row.id,
            dept_code=row.dept_code,
            dept_name=row.dept_name,
            created_at=row.created_at,
            user_count=row.user_count,
        )
        for row in rows
    ]
    return BaseResp.ok(result)


# ------------------------------------------------------------------
# POST /
# ------------------------------------------------------------------

@router.post("/", response_model=BaseResp[DeptOut], status_code=status.HTTP_201_CREATED)
async def create_department(
    req: DeptCreate,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """新建部门。dept_code 唯一，大写字母/数字。"""
    code = req.dept_code.upper()

    # dept_code 唯一性校验
    existing = await db.scalar(select(Department).where(Department.dept_code == code))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": 40900, "message": f"部门代码 {code} 已存在"},
        )

    dept = Department(dept_code=code, dept_name=req.dept_name)
    db.add(dept)
    await db.flush()   # 获取自增 id

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.DEPT_CREATE,
        resource_type="department",
        resource_id=str(dept.id),
        new_value={"dept_code": dept.dept_code, "dept_name": dept.dept_name},
        ip_address=_get_ip(request),
    )

    logger.info("Department created | code={code} | by={operator}", code=dept.dept_code, operator=current_user.username)

    return BaseResp.ok(
        DeptOut(
            id=dept.id,
            dept_code=dept.dept_code,
            dept_name=dept.dept_name,
            created_at=dept.created_at,
            user_count=0,
        )
    )


# ------------------------------------------------------------------
# PATCH /{dept_id}
# ------------------------------------------------------------------

@router.patch("/{dept_id}", response_model=BaseResp[DeptOut])
async def update_department(
    dept_id: int,
    req: DeptUpdate,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """修改部门名称（dept_code 不可修改）。"""
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 40400, "message": "部门不存在"},
        )

    old_name = dept.dept_name
    dept.dept_name = req.dept_name

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.DEPT_UPDATE,
        resource_type="department",
        resource_id=str(dept.id),
        old_value={"dept_name": old_name},
        new_value={"dept_name": dept.dept_name},
        ip_address=_get_ip(request),
    )

    user_count = await db.scalar(
        select(func.count(User.id)).where(User.dept_id == dept_id)
    )

    logger.info("Department updated | dept_id={dept_id} | by={operator}", dept_id=dept.id, operator=current_user.username)

    return BaseResp.ok(
        DeptOut(
            id=dept.id,
            dept_code=dept.dept_code,
            dept_name=dept.dept_name,
            created_at=dept.created_at,
            user_count=user_count or 0,
        )
    )


# ------------------------------------------------------------------
# DELETE /{dept_id}
# ------------------------------------------------------------------

@router.delete("/{dept_id}", response_model=BaseResp[None])
async def delete_department(
    dept_id: int,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除部门。部门下仍有用户或文档时拒绝删除。"""
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 40400, "message": "部门不存在"},
        )

    # 有关联用户则拒绝
    user_count = await db.scalar(
        select(func.count(User.id)).where(User.dept_id == dept_id)
    )
    if user_count and user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": 40901, "message": f"部门下还有 {user_count} 名用户，请先转移或删除用户"},
        )

    # 有关联文档则拒绝
    doc_count = await db.scalar(
        select(func.count(Document.id)).where(Document.dept_id == dept_id)
    )
    if doc_count and doc_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": 40902, "message": f"部门下还有 {doc_count} 份文档，请先归档或删除文档"},
        )

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.DEPT_DELETE,
        resource_type="department",
        resource_id=str(dept.id),
        old_value={"dept_code": dept.dept_code, "dept_name": dept.dept_name},
        ip_address=_get_ip(request),
    )

    await db.delete(dept)

    logger.info("Department deleted | dept_id={dept_id} | code={code} | by={operator}", dept_id=dept_id, code=dept.dept_code, operator=current_user.username)

    return BaseResp.ok(message="部门已删除")
