"""Windows 冒烟：起 uvicorn → health/登录/聊天流 → 关服务。"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[2]
os.chdir(BACKEND)
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def port_free(p: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


async def smoke_api() -> bool:
    ok = True
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as client:
        health = None
        for _ in range(40):
            try:
                r = await client.get("/health")
                if r.status_code == 200:
                    health = r.json()
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        print("health:", health)
        if health != {"status": "ok"}:
            return False

        r = await client.get("/openapi.json")
        print("openapi:", r.status_code, "paths", len(r.json().get("paths", {})))

        token = None
        for user, pwd in (
            ("zhangsan", "Demo@12345"),
            ("admin", os.getenv("ADMIN_INIT_PASSWORD", "Admin@123")),
        ):
            login = await client.post("/api/auth/login", json={"username": user, "password": pwd})
            print(f"login {user}:", login.status_code)
            if login.status_code == 200:
                body = login.json()
                token = (body.get("data") or {}).get("access_token") or body.get("access_token")
                if token:
                    break
        if not token:
            return False

        h = {"Authorization": f"Bearer {token}"}
        r = await client.get("/api/auth/me", headers=h)
        print("me:", r.status_code, r.text[:180])
        r = await client.get("/api/docs/", headers=h)
        print("docs list:", r.status_code)

        # 流式闲聊（可走外部 API；失败不阻断路由验收，但记 FAIL）
        try:
            events = []
            async with client.stream(
                "POST",
                "/api/chat/stream",
                json={"query": "你好"},
                headers=h,
                timeout=httpx.Timeout(10.0, read=120.0),
            ) as resp:
                print("chat stream status:", resp.status_code)
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        ev = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    events.append(ev.get("type"))
                    if ev.get("type") in ("done", "error"):
                        print("chat event:", ev.get("type"), str(ev.get("content"))[:150])
                        break
            print("chat event types:", events[:25])
            if "done" not in events and "error" not in events:
                ok = False
            elif events and events[-1] == "error":
                ok = False
        except Exception as exc:
            print("chat stream fail:", type(exc).__name__, exc)
            ok = False
    return ok


def main() -> int:
    if not port_free(PORT):
        print(f"port {PORT} busy")
        return 2
    log = BACKEND / "logs" / "uvicorn_smoke.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(BACKEND),
        stdout=logf,
        stderr=subprocess.STDOUT,
    )
    print(f"uvicorn pid={proc.pid}")
    try:
        if proc.poll() is not None:
            print(log.read_text(encoding="utf-8", errors="replace")[-2500:])
            return 1
        ok = asyncio.run(smoke_api())
        text = log.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if any(k in line for k in ("prompts", "scheduler", "WorkPilot v2 starting", "llm] routing")):
                print(" |", line[:220])
        print("SMOKE", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        logf.close()
        print("uvicorn stopped")


if __name__ == "__main__":
    raise SystemExit(main())
