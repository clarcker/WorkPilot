"""
文档管理路由。

POST   /api/docs/upload              上传文档（触发后台处理流水线）
GET    /api/docs                     列出文档（分页 + 过滤）
GET    /api/docs/{id}                文档详情（含分块数量）
PATCH  /api/docs/{id}                修改元数据（visibility / category / version）
DELETE /api/docs/{id}                归档（软删除，status = archived）
POST   /api/docs/{id}/reindex        重新触发向量化流水线
GET    /api/docs/{id}/permissions    获取指定人员白名单（specific_users 模式）
PUT    /api/docs/{id}/permissions    替换指定人员白名单

权限规则：
  super_admin  — 操作所有部门的文档
  dept_admin   — 只能操作本部门的文档
"""
from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import AuditAction, write_audit
from core.config import settings
from core.deps import require_admin
from core.logger import logger
from db.models import (
    Department,
    DocChunk,
    DocPermission,
    DocStatus,
    DocVisibility,
    Document,
    User,
    UserRole,
)
from db.session import get_db
from schemas.common import BaseResp, PagedData
from schemas.documents import DocOut, DocPermissionSet, DocUpdate, PermissionMember
from services.document_pipeline import run_pipeline

router = APIRouter()

# 支持的文件类型
_ALLOWED_TYPES = {"pdf", "docx", "doc", "txt", "md"}


def _get_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _load_doc(db: AsyncSession, doc_id: int) -> Document:
    doc = await db.scalar(
        select(Document)
        .options(
            selectinload(Document.department),
            selectinload(Document.uploaded_by_user),
        )
        .where(Document.id == doc_id)
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 40400, "message": "文档不存在"},
        )
    return doc


def _check_doc_scope(actor: User, doc: Document) -> None:
    """dept_admin 只能操作本部门文档；super_admin 无限制。"""
    if actor.role == UserRole.super_admin:
        return
    if doc.dept_id != actor.dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40301, "message": "无权操作其他部门的文档"},
        )


def _doc_to_out(doc: Document, chunk_count: int | None = None) -> DocOut:
    dept_name = doc.department.dept_name if doc.department else None
    uploader_name = doc.uploaded_by_user.real_name if doc.uploaded_by_user else None
    return DocOut(
        id=doc.id,
        file_uuid=doc.file_uuid,
        file_name=doc.file_name,
        file_size=doc.file_size,
        file_type=doc.file_type,
        dept_id=doc.dept_id,
        dept_name=dept_name,
        visibility=doc.visibility.value,
        status=doc.status.value,
        error_message=doc.error_message,
        category=doc.category,
        version=doc.version,
        uploaded_by=doc.uploaded_by,
        uploaded_by_name=uploader_name,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        chunk_count=chunk_count,
    )


# ------------------------------------------------------------------
# POST /upload
# ------------------------------------------------------------------

@router.post("/upload", response_model=BaseResp[DocOut], status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(..., description="支持 .pdf / .docx / .md"),
    dept_id: int | None = Form(default=None, description="目标部门（super_admin 必填，dept_admin 忽略此字段）"),
    visibility: str = Form(default="dept_only"),
    category: str | None = Form(default=None),
    version:  str | None = Form(default=None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # ---- 文件类型校验 ----
    original_name = file.filename or "unknown"
    suffix = Path(original_name).suffix.lower().lstrip(".")
    if suffix not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": 42200, "message": f"不支持的文件类型 .{suffix}，支持：pdf / docx / doc / txt / md"},
        )

    # ---- 文件大小校验（先读元数据，避免完整读取）----
    if file.size and file.size > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": 41300, "message": f"文件超过最大限制 {settings.max_file_size_mb} MB"},
        )

    # ---- 确定目标部门 ----
    if current_user.role == UserRole.dept_admin:
        target_dept_id = current_user.dept_id
    else:
        if dept_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": 42200, "message": "super_admin 上传文档时必须指定 dept_id"},
            )
        target_dept_id = dept_id

    if not await db.get(Department, target_dept_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40400, "message": "指定部门不存在"},
        )

    # ---- 校验 visibility ----
    try:
        vis = DocVisibility(visibility)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": 42200, "message": f"无效 visibility 值：{visibility}"},
        )

    # ---- 保存文件到磁盘 ----
    file_uuid = str(uuid.uuid4())
    save_dir = Path(settings.upload_dir) / str(target_dept_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{file_uuid}.{suffix}"

    content = await file.read()
    actual_size = len(content)

    # 再次检查实际大小（前面 file.size 可能是 None）
    if actual_size > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": 41300, "message": f"文件超过最大限制 {settings.max_file_size_mb} MB"},
        )

    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    # ---- 写 Document 记录 ----
    doc = Document(
        file_uuid=file_uuid,
        file_name=original_name,
        file_size=actual_size,
        file_type=suffix,
        storage_path=str(save_path),
        dept_id=target_dept_id,
        visibility=vis,
        status=DocStatus.processing,
        category=category,
        version=version,
        uploaded_by=current_user.id,
    )
    db.add(doc)
    await db.flush()

    # 加载关联用于响应
    await db.refresh(doc, attribute_names=["department", "uploaded_by_user"])

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.DOC_UPLOAD,
        resource_type="document",
        resource_id=str(doc.id),
        new_value={
            "file_name": doc.file_name,
            "file_size": doc.file_size,
            "dept_id": doc.dept_id,
            "visibility": doc.visibility.value,
        },
        ip_address=_get_ip(request),
    )

    # ---- 触发后台流水线 ----
    # 必须先提交事务，否则 background task 中的独立 session 看不到文档
    await db.commit()
    doc_id = doc.id
    background_tasks.add_task(run_pipeline, doc_id)

    logger.info("Document uploaded | doc_id={doc_id} | file={filename} | by={operator}", doc_id=doc.id, filename=doc.file_name, operator=current_user.username)

    return BaseResp.ok(_doc_to_out(doc), message="文件上传成功，正在后台处理")


# ------------------------------------------------------------------
# GET /   列出文档
# ------------------------------------------------------------------

@router.get("/", response_model=BaseResp[PagedData[DocOut]])
async def list_documents(
    page:       int        = Query(default=1,    ge=1),
    page_size:  int        = Query(default=20,   ge=1, le=100),
    dept_id:    int | None = Query(default=None),
    status_:    str | None = Query(default=None, alias="status"),
    keyword:    str | None = Query(default=None, max_length=100),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    conditions = [Document.status != DocStatus.archived]  # 默认不显示已归档

    if current_user.role == UserRole.dept_admin:
        conditions.append(Document.dept_id == current_user.dept_id)
    elif dept_id is not None:
        conditions.append(Document.dept_id == dept_id)

    if status_:
        try:
            conditions.append(Document.status == DocStatus(status_))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": 42200, "message": f"无效 status 值：{status_}"},
            )

    if keyword:
        conditions.append(Document.file_name.ilike(f"%{keyword}%"))

    # 总数
    count_stmt = select(func.count(Document.id))
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
    total = await db.scalar(count_stmt) or 0

    # 数据
    data_stmt = (
        select(Document)
        .options(
            selectinload(Document.department),
            selectinload(Document.uploaded_by_user),
        )
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    for cond in conditions:
        data_stmt = data_stmt.where(cond)
    rows = await db.execute(data_stmt)
    docs = rows.scalars().all()

    return BaseResp.ok(
        PagedData(
            items=[_doc_to_out(d) for d in docs],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


# ------------------------------------------------------------------
# GET /{doc_id}   文档详情
# ------------------------------------------------------------------

@router.get("/{doc_id}", response_model=BaseResp[DocOut])
async def get_document(
    doc_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await _load_doc(db, doc_id)
    _check_doc_scope(current_user, doc)

    chunk_count = await db.scalar(
        select(func.count(DocChunk.id)).where(DocChunk.doc_id == doc_id)
    )
    return BaseResp.ok(_doc_to_out(doc, chunk_count=chunk_count or 0))


# ------------------------------------------------------------------
# PATCH /{doc_id}   修改元数据
# ------------------------------------------------------------------

@router.patch("/{doc_id}", response_model=BaseResp[DocOut])
async def update_document(
    doc_id: int,
    req: DocUpdate,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await _load_doc(db, doc_id)
    _check_doc_scope(current_user, doc)

    if doc.status == DocStatus.archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40300, "message": "已归档文档不可修改"},
        )

    old_val: dict = {}
    new_val: dict = {}

    if req.visibility is not None:
        try:
            new_vis = DocVisibility(req.visibility)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": 42200, "message": f"无效 visibility 值：{req.visibility}"},
            )
        old_val["visibility"] = doc.visibility.value
        doc.visibility = new_vis
        new_val["visibility"] = new_vis.value

    if req.category is not None:
        old_val["category"] = doc.category
        doc.category = req.category
        new_val["category"] = req.category

    if req.version is not None:
        old_val["version"] = doc.version
        doc.version = req.version
        new_val["version"] = req.version

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.DOC_UPDATE,
        resource_type="document",
        resource_id=str(doc.id),
        old_value=old_val or None,
        new_value=new_val or None,
        ip_address=_get_ip(request),
    )

    # 显式 flush：将修改写入 DB，触发服务端 updated_at 计算。
    # 之后 doc 所有属性（含 updated_at）均 expire，不可直接访问。
    await db.flush()

    # 两个独立 SELECT，此时 session 无 dirty 对象，不会再触发 autoflush。
    chunk_count = await db.scalar(
        select(func.count(DocChunk.id)).where(DocChunk.doc_id == doc_id)
    )
    # 重新查询拿到最新 updated_at 及已 expire 的关联
    doc = await db.scalar(
        select(Document)
        .options(
            selectinload(Document.department),
            selectinload(Document.uploaded_by_user),
        )
        .where(Document.id == doc_id)
    )

    logger.info("Document updated | doc_id={doc_id} | by={operator}", doc_id=doc_id, operator=current_user.username)

    return BaseResp.ok(_doc_to_out(doc, chunk_count=chunk_count or 0))


# ------------------------------------------------------------------
# DELETE /{doc_id}   归档（软删除）
# ------------------------------------------------------------------

@router.delete("/{doc_id}", response_model=BaseResp[None])
async def archive_document(
    doc_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await _load_doc(db, doc_id)
    _check_doc_scope(current_user, doc)

    if doc.status == DocStatus.archived:
        return BaseResp.ok(message="文档已是归档状态")

    doc.status = DocStatus.archived

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.DOC_ARCHIVE,
        resource_type="document",
        resource_id=str(doc.id),
        old_value={"status": "active"},
        ip_address=_get_ip(request),
    )

    logger.info("Document archived | doc_id={doc_id} | by={operator}", doc_id=doc_id, operator=current_user.username)

    return BaseResp.ok(message="文档已归档")


# ------------------------------------------------------------------
# POST /{doc_id}/reindex   重新触发向量化
# ------------------------------------------------------------------

@router.post("/{doc_id}/reindex", response_model=BaseResp[DocOut])
async def reindex_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await _load_doc(db, doc_id)
    _check_doc_scope(current_user, doc)

    if doc.status == DocStatus.archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40300, "message": "已归档文档不可重新索引"},
        )

    if doc.status == DocStatus.processing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": 40900, "message": "文档正在处理中，请稍后再试"},
        )

    doc.status = DocStatus.processing
    doc.error_message = None

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.DOC_UPDATE,
        resource_type="document",
        resource_id=str(doc.id),
        new_value={"action": "reindex"},
        ip_address=_get_ip(request),
    )

    # 必须先提交事务，否则 background task 中的独立 session 看不到状态更新
    await db.commit()

    background_tasks.add_task(run_pipeline, doc_id)

    # 重新加载 doc 获取最新状态
    doc = await db.scalar(
        select(Document)
        .options(
            selectinload(Document.department),
            selectinload(Document.uploaded_by_user),
        )
        .where(Document.id == doc_id)
    )

    logger.info("Document reindex triggered | doc_id={doc_id} | by={operator}", doc_id=doc_id, operator=current_user.username)

    return BaseResp.ok(_doc_to_out(doc), message="已重新触发索引，正在后台处理")


# ------------------------------------------------------------------
# GET /{doc_id}/permissions   查看指定人员白名单
# ------------------------------------------------------------------

@router.get("/{doc_id}/permissions", response_model=BaseResp[list[PermissionMember]])
async def get_doc_permissions(
    doc_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await _load_doc(db, doc_id)
    _check_doc_scope(current_user, doc)

    rows = await db.execute(
        select(DocPermission, User)
        .join(User, User.id == DocPermission.user_id)
        .where(DocPermission.doc_id == doc_id)
        .order_by(DocPermission.granted_at)
    )
    members = [
        PermissionMember(
            user_id=perm.user_id,
            username=user.username,
            real_name=user.real_name,
            employee_no=user.employee_no,
            granted_at=perm.granted_at,
        )
        for perm, user in rows
    ]
    return BaseResp.ok(members)


# ------------------------------------------------------------------
# PUT /{doc_id}/permissions   替换整个白名单
# ------------------------------------------------------------------

@router.put("/{doc_id}/permissions", response_model=BaseResp[list[PermissionMember]])
async def set_doc_permissions(
    doc_id: int,
    req: DocPermissionSet,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await _load_doc(db, doc_id)
    _check_doc_scope(current_user, doc)

    if doc.status == DocStatus.archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40300, "message": "已归档文档不可修改权限"},
        )

    # 验证所有 user_id 存在且属于本部门（dept_admin 限制；super_admin 不限）
    valid_user_ids: list[int] = []
    for uid in set(req.user_ids):
        user = await db.get(User, uid)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": 40400, "message": f"用户 ID {uid} 不存在"},
            )
        if current_user.role == UserRole.dept_admin and user.dept_id != current_user.dept_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "message": f"用户 {user.real_name} 不属于本部门"},
            )
        valid_user_ids.append(uid)

    # 清空旧白名单，写入新白名单
    await db.execute(delete(DocPermission).where(DocPermission.doc_id == doc_id))
    for uid in valid_user_ids:
        db.add(DocPermission(doc_id=doc_id, user_id=uid, granted_by=current_user.id))

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.DOC_PERM_UPDATE,
        resource_type="document",
        resource_id=str(doc_id),
        new_value={"user_ids": valid_user_ids},
        ip_address=_get_ip(request),
    )

    # 返回最新白名单
    await db.flush()
    rows = await db.execute(
        select(DocPermission, User)
        .join(User, User.id == DocPermission.user_id)
        .where(DocPermission.doc_id == doc_id)
        .order_by(DocPermission.granted_at)
    )
    members = [
        PermissionMember(
            user_id=perm.user_id,
            username=user.username,
            real_name=user.real_name,
            employee_no=user.employee_no,
            granted_at=perm.granted_at,
        )
        for perm, user in rows
    ]

    logger.info("Document permissions updated | doc_id={doc_id} | user_count={count} | by={operator}", doc_id=doc_id, count=len(valid_user_ids), operator=current_user.username)

    return BaseResp.ok(members)
