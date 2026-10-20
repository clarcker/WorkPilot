"""会话上限 / 消息上限 / 配置读取（mock DB，不依赖真实库）。"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.chat import _enforce_message_limit, _enforce_session_limit, _get_int_config
from db.models import Conversation, ConversationStatus


def _scalar_result(value):
    m = MagicMock()
    m.scalar = AsyncMock(return_value=value)
    return m


def _execute_result(rows):
    m = MagicMock()
    m.scalars = MagicMock()
    m.scalars.return_value.all = MagicMock(return_value=rows)
    m.all = MagicMock(return_value=rows)
    return m


@pytest.mark.no_db
class TestGetIntConfig:
    @pytest.mark.asyncio
    async def test_missing_key_returns_default(self):
        db = MagicMock()
        db.scalar = AsyncMock(return_value=None)
        assert await _get_int_config(db, "max_sessions_per_user", 200) == 200

    @pytest.mark.asyncio
    async def test_dict_wrapped_value(self):
        db = MagicMock()
        db.scalar = AsyncMock(return_value={"value": 50})
        assert await _get_int_config(db, "max_sessions_per_user", 200) == 50

    @pytest.mark.asyncio
    async def test_invalid_value_returns_default(self):
        db = MagicMock()
        db.scalar = AsyncMock(return_value="not-a-number")
        assert await _get_int_config(db, "k", 200) == 200

    @pytest.mark.asyncio
    async def test_non_positive_returns_default(self):
        db = MagicMock()
        db.scalar = AsyncMock(return_value=0)
        assert await _get_int_config(db, "k", 200) == 200


@pytest.mark.no_db
class TestEnforceSessionLimit:
    @pytest.mark.asyncio
    async def test_under_limit_no_archive(self):
        db = MagicMock()
        db.scalar = AsyncMock(return_value=5)
        n = await _enforce_session_limit(db, user_id=1, max_sessions=200)
        assert n == 0

    @pytest.mark.asyncio
    async def test_at_limit_archives_oldest(self):
        old1 = Conversation(
            id=1, user_id=1, title="a",
            status=ConversationStatus.active, message_count=2,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        old2 = Conversation(
            id=2, user_id=1, title="b",
            status=ConversationStatus.active, message_count=2,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db = MagicMock()
        # count = 3, limit = 2 → overflow = 3-2+1 = 2
        db.scalar = AsyncMock(return_value=3)
        db.execute = AsyncMock(return_value=_execute_result([old1, old2]))

        n = await _enforce_session_limit(db, user_id=1, max_sessions=2)
        assert n == 2
        assert old1.status == ConversationStatus.archived
        assert old2.status == ConversationStatus.archived


@pytest.mark.no_db
class TestEnforceMessageLimit:
    @pytest.mark.asyncio
    async def test_under_limit_no_delete(self):
        conv = Conversation(
            id=1, user_id=1, title="t",
            status=ConversationStatus.active, message_count=10,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db = MagicMock()
        n = await _enforce_message_limit(db, conv, max_messages=500)
        assert n == 0
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_over_limit_deletes_oldest(self):
        conv = Conversation(
            id=1, user_id=1, title="t",
            status=ConversationStatus.active, message_count=10,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db = MagicMock()
        # overflow = 10 - 8 + 2 = 4
        db.execute = AsyncMock(
            side_effect=[
                _execute_result([(1,), (2,), (3,), (4,)]),  # select ids
                MagicMock(rowcount=4),                       # delete
            ]
        )
        n = await _enforce_message_limit(db, conv, max_messages=8)
        assert n == 4
        assert conv.message_count == 6
