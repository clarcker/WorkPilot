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
from dotenv import load_dotenv

load_dotenv()

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

        # 额度（按用户职级取 annual_max，已用部分示例）
        used_samples = {
            ("zhangsan", "差旅住宿"): 12300,
            ("zhangsan", "交通补贴"): 5600,
            ("zhangsan", "餐饮补贴"): 8200,
            ("zhangsan", "通讯补贴"): 1800,
        }
        for username, uid in user_ids.items():
            # 查职级
            jl = await db.scalar(
                text("SELECT job_level FROM users WHERE id=:i"), {"i": uid}
            )
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
        print("报销额度已写入")
        await db.commit()

    await engine.dispose()
    print("seed_demo 完成")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
