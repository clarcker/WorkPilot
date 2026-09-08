from sqlalchemy.orm import DeclarativeBase, MappedColumn
from sqlalchemy import DateTime, func
from typing import Annotated
import datetime

# 公共时间戳列类型（所有表共用）
timestamp_now = Annotated[
    datetime.datetime,
    MappedColumn(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
]


class Base(DeclarativeBase):
    pass
