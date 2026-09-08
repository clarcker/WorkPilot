# 问题总结 2026-06-25

## 2026-06-25 15:10 - pytest 因 conftest.py 数据库连接失败导致单元测试无法运行

### 背景

编写 `backend/tests/unit/test_tools.py` 单元测试后，运行 pytest 时所有测试在 setup 阶段报错。

### 问题现象

```
RuntimeError: Test database setup failed: [Errno 10061] Connect call failed ('127.0.0.1', 5433)
```

所有 10 个测试用例均报此错误，无法执行任何测试。

### 原因分析

`backend/tests/conftest.py` 中定义了 `setup_test_database` fixture，标记为 `scope="session", autouse=True`。该 fixture 尝试连接 PostgreSQL 数据库（端口 5433），但本地未运行数据库服务。由于是 autouse，所有测试（包括不依赖数据库的单元测试）都会触发此 fixture。

### 解决方案

在 `backend/tests/unit/conftest.py` 中创建同名 fixture 覆盖父级 conftest 的行为，使其成为 no-op：

```python
@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    yield

@pytest.fixture(autouse=True)
def cleanup_tables():
    yield
```

### 涉及文件

- `backend/tests/unit/conftest.py`（新建）
- `backend/tests/conftest.py`（原有，未修改）

### 经验总结

当项目有全局 autouse fixture（如数据库 setup）时，纯单元测试目录需要创建自己的 conftest.py 覆盖这些 fixture，避免不必要的依赖。
