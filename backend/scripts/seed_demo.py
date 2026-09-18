"""
一键演示数据：部门 / 用户 / 报销规则与额度。

用法：
    cd backend
    uv run python scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio
import sys

import bcrypt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from core.config import settings  # noqa: E402

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://workpilot:workpilot@localhost:5432/workpilot",
)

DEFAULT_PWD = "Demo@12345"

# 职级 → 各类别 (daily_max, annual_max)
# 差旅住宿 senior=500：与《差旅报销管理办法》示例一致，便于演示「日均 600 超标」
RULES = {
    "差旅住宿": {
        "junior": (400, 30000),
        "mid":    (500, 40000),
        "senior": (500, 50000),
        "lead":   (700, 60000),
    },
    "交通补贴": {
        "junior": (150, 12000),
        "mid":    (200, 16000),
        "senior": (250, 20000),
        "lead":   (300, 24000),
    },
    "餐饮补贴": {
        "junior": (80, 10000),
        "mid":    (100, 12000),
        "senior": (120, 15000),
        "lead":   (150, 18000),
    },
    "通讯补贴": {
        "junior": (200, 1800),
        "mid":    (300, 2400),
        "senior": (300, 3600),
        "lead":   (400, 4800),
    },
}

DOC_REFS = {
    "差旅住宿": "《差旅报销管理办法》第 3.2 条",
    "交通补贴": "《差旅报销管理办法》第 4.1 条",
    "餐饮补贴": "《差旅报销管理办法》第 4.3 条",
    "通讯补贴": "《福利补贴制度》第 2.1 条",
}

DEPTS = [
    ("RD", "研发部"),
    ("HR", "人力资源部"),
    ("CS", "客服部"),
]

# username, real_name, role, dept_code, job_level, employee_no
USERS = [
    ("zhangsan", "张三", "employee", "RD", "senior", "RD001"),
    ("lisi",     "李四", "employee", "HR", "mid",    "HR001"),
    ("wangwu",   "王五", "employee", "RD", "junior", "RD002"),
    ("zhaoliu",  "赵六", "employee", "CS", "mid",    "CS001"),
    ("rdadmin",  "研发管理员", "dept_admin", "RD", "lead", "RD010"),
    ("hradmin",  "人力管理员", "dept_admin", "HR", "lead", "HR010"),
]


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    pwd_hash = bcrypt.hashpw(DEFAULT_PWD.encode(), bcrypt.gensalt(rounds=12)).decode()

    async with Session() as db:  # type: AsyncSession
        # 部门
        dept_ids: dict[str, int] = {}
        for code, name in DEPTS:
            row = await db.scalar(
                text("SELECT id FROM departments WHERE dept_code = :c"), {"c": code}
            )
            if not row:
                await db.execute(
                    text("INSERT INTO departments (dept_code, dept_name) VALUES (:c, :n)"),
                    {"c": code, "n": name},
                )
                row = await db.scalar(
                    text("SELECT id FROM departments WHERE dept_code = :c"), {"c": code}
                )
            dept_ids[code] = int(row)
        print(f"部门: {dept_ids}")

        # 用户
        user_ids: dict[str, int] = {}
        for username, real_name, role, dept_code, job_level, emp_no in USERS:
            uid = await db.scalar(
                text("SELECT id FROM users WHERE username = :u"), {"u": username}
            )
            if uid:
                await db.execute(
                    text(
                        "UPDATE users SET job_level=:jl, is_active=true, "
                        "must_change_password=false, failed_login_count=0 "
                        "WHERE username=:u"
                    ),
                    {"jl": job_level, "u": username},
                )
                user_ids[username] = int(uid)
                continue
            await db.execute(
                text(
                    """
                    INSERT INTO users (
                        username, employee_no, display_name, real_name, dept_id, role,
                        job_level, password_hash, must_change_password, is_active
                    ) VALUES (
                        :u, :eno, :dn, :rn, :did, :role,
                        :jl, :ph, false, true
                    )
                    """
                ),
                {
                    "u": username,
                    "eno": emp_no,
                    "dn": real_name,
                    "rn": real_name,
                    "did": dept_ids[dept_code],
                    "role": role,
                    "jl": job_level,
                    "ph": pwd_hash,
                },
            )
            uid = await db.scalar(
                text("SELECT id FROM users WHERE username = :u"), {"u": username}
            )
            user_ids[username] = int(uid)
        print(f"用户: {user_ids}  默认密码: {DEFAULT_PWD}")

        # 报销规则
        for category, levels in RULES.items():
            for level, (daily, annual) in levels.items():
                exists = await db.scalar(
                    text(
                        "SELECT id FROM reimbursement_rules "
                        "WHERE category=:c AND job_level=:j"
                    ),
                    {"c": category, "j": level},
                )
                if exists:
                    await db.execute(
                        text(
                            "UPDATE reimbursement_rules SET daily_max=:d, annual_max=:a, doc_ref=:ref "
                            "WHERE id=:i"
                        ),
                        {
                            "d": daily,
                            "a": annual,
                            "ref": DOC_REFS.get(category),
                            "i": exists,
                        },
                    )
                    continue
                await db.execute(
                    text(
                        """
                        INSERT INTO reimbursement_rules
                            (category, job_level, daily_max, annual_max, doc_ref)
                        VALUES (:c, :j, :d, :a, :ref)
                        """
                    ),
                    {
                        "c": category,
                        "j": level,
                        "d": daily,
                        "a": annual,
                        "ref": DOC_REFS.get(category),
                    },
                )
        print("报销规则已写入")

        # 额度（按用户职级取 annual_max；示例已用金额）
        # eval 超管 user_id=1 也需四类额度，否则 case_014 通讯补贴失败
        used_samples = {
            ("zhangsan", "差旅住宿"): 12300,
            ("zhangsan", "交通补贴"): 5600,
            ("zhangsan", "餐饮补贴"): 8200,
            ("zhangsan", "通讯补贴"): 1800,
        }
        # 除 seed 用户外，给库里已有用户（含 admin）也补额度
        extra_users = (
            await db.execute(text("SELECT id, job_level FROM users WHERE is_active = true"))
        ).all()
        target_users = {**user_ids}
        for row in extra_users:
            target_users[f"_id_{row[0]}"] = int(row[0])

        for username, uid in target_users.items():
            jl = await db.scalar(
                text("SELECT job_level FROM users WHERE id=:i"), {"i": uid}
            )
            jl = jl or "mid"
            for category in RULES:
                annual = RULES[category].get(jl, RULES[category]["mid"])[1]
                used = used_samples.get((username, category), 0)
                exists = await db.scalar(
                    text(
                        "SELECT id FROM reimbursement_limits "
                        "WHERE user_id=:u AND category=:c"
                    ),
                    {"u": uid, "c": category},
                )
                if exists:
                    await db.execute(
                        text(
                            "UPDATE reimbursement_limits SET annual_max=:a, used=:used "
                            "WHERE id=:i"
                        ),
                        {"a": annual, "used": used, "i": exists},
                    )
                else:
                    await db.execute(
                        text(
                            """
                            INSERT INTO reimbursement_limits
                                (user_id, category, annual_max, used)
                            VALUES (:u, :c, :a, :used)
                            """
                        ),
                        {"u": uid, "c": category, "a": annual, "used": used},
                    )
        print("报销额度已写入（含全部在职用户）")
        await db.commit()

    # ── 场景 D：制度文档（四级可见性）────────────────────────
    await seed_documents(engine, dept_ids, user_ids)

    await engine.dispose()
    print("seed_demo 完成")


# 场景 D 文档清单：文件名 → (visibility, dept_code 或 None, specific_usernames)
# 来源：仓库根目录 test/*.md
DOC_SPECS = [
    ("报销管理制度.md",           "global",         None, []),
    ("考勤与休假制度.md",         "global",         None, []),
    ("新员工入职指南.md",         "global",         None, []),
    ("信息安全与合规制度.md",     "global",         None, []),
    ("IT设备与运维服务规范.md",   "non_customer",   None, []),          # 客服不可见
    ("薪酬调整实施方案-受限.md",  "specific_users", "RD", ["zhangsan", "rdadmin"]),  # 白名单
]


async def seed_documents(engine, dept_ids: dict[str, int], user_ids: dict[str, int]) -> None:
    """
    把 test/ 下制度文档灌入 documents + doc_chunks + embeddings。

    幂等：同名 ready 文档跳过；需要重建请先归档或改用 reindex 接口。
    """
    import shutil
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    src_dir = project_root / "test"
    upload_dir = Path(settings.upload_dir)
    if not str(upload_dir):
        upload_dir = backend_root / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    if not src_dir.exists():
        print(f"[warn] 未找到 {src_dir}，跳过文档 seed")
        return

    # 延迟导入，避免 seed 纯数据时强依赖 Ollama
    from sqlalchemy import select
    from db.models import DocChunk, DocPermission, DocStatus, Document, DocVisibility, Embedding
    from services.chunker import chunk_segments
    from services.document_parser import parse_document
    from services.embedder import get_embeddings_batch
    from services.fts import tokenize_for_search

    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    admin_id = user_ids.get("rdadmin") or next(iter(user_ids.values()))

    async with Session() as db:
        for fname, visibility, dept_code, whitelist in DOC_SPECS:
            src = src_dir / fname
            if not src.exists():
                print(f"[warn] 缺少 {src}，跳过")
                continue

            existing = await db.scalar(
                select(Document).where(
                    Document.file_name == fname,
                    Document.status == DocStatus.ready,
                )
            )
            if existing:
                # 场景 D：校正已有文档的可见性 / 白名单，保证演示可复现
                changed = False
                if existing.visibility.value != visibility:
                    existing.visibility = DocVisibility(visibility)
                    changed = True
                if visibility == "specific_users":
                    for uname in whitelist:
                        uid = user_ids.get(uname)
                        if not uid:
                            continue
                        has = await db.scalar(
                            select(DocPermission).where(
                                DocPermission.doc_id == existing.id,
                                DocPermission.user_id == uid,
                            )
                        )
                        if not has:
                            db.add(DocPermission(
                                doc_id=existing.id,
                                user_id=uid,
                                granted_by=admin_id,
                            ))
                            changed = True
                if changed:
                    await db.commit()
                    print(f"  已校正可见性: {fname} → {visibility}")
                else:
                    print(f"  文档已存在，跳过: {fname}")
                continue

            dest = upload_dir / fname
            shutil.copy2(src, dest)

            dept_id = dept_ids.get(dept_code) if dept_code else dept_ids["HR"]
            if not dept_id:
                dept_id = next(iter(dept_ids.values()))

            doc = Document(
                file_name=fname,
                file_size=src.stat().st_size,
                file_type="md",
                storage_path=str(dest),
                dept_id=dept_id,
                visibility=DocVisibility(visibility),
                status=DocStatus.processing,
                category="制度",
                version="v1",
                uploaded_by=admin_id,
            )
            db.add(doc)
            await db.flush()

            try:
                segments = parse_document(str(dest), "md")
                chunks_data = chunk_segments(segments)
                texts = [c["content"] for c in chunks_data]
                embeddings_list = await get_embeddings_batch(texts)

                for chunk_data, vec in zip(chunks_data, embeddings_list):
                    chunk = DocChunk(
                        doc_id=doc.id,
                        chunk_index=chunk_data["chunk_index"],
                        content=chunk_data["content"],
                        page_no=chunk_data["page_no"],
                        heading=chunk_data["heading"],
                        token_count=len(chunk_data["content"]),
                    )
                    db.add(chunk)
                    await db.flush()
                    tok = tokenize_for_search(chunk_data["content"])
                    if tok:
                        from sqlalchemy import text as sa_text
                        await db.execute(
                            sa_text(
                                "UPDATE doc_chunks SET content_tsv = "
                                "to_tsvector('simple', :tok) WHERE id = :id"
                            ),
                            {"tok": tok, "id": chunk.id},
                        )
                    db.add(Embedding(
                        chunk_id=chunk.id,
                        doc_id=doc.id,
                        dept_id=dept_id,
                        embedding=vec,
                        model_name=settings.ollama_embed_model,
                    ))

                # specific_users 白名单
                if visibility == "specific_users":
                    for uname in whitelist:
                        uid = user_ids.get(uname)
                        if uid:
                            db.add(DocPermission(
                                doc_id=doc.id,
                                user_id=uid,
                                granted_by=admin_id,
                            ))

                doc.status = DocStatus.ready
                await db.commit()
                print(f"  已入库: {fname} | visibility={visibility} | chunks={len(chunks_data)}")
            except Exception as exc:
                await db.rollback()
                print(f"[error] 文档入库失败 {fname}: {exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
