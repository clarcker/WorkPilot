"""logger 模块单元测试"""
from core.logger import (
    logger,
    setup_logger,
    get_logger_with_context,
    generate_request_id,
    request_id_var,
    user_id_var,
    RequestLoggingMiddleware,
)


class TestLogContextVars:
    """测试请求追踪上下文变量"""

    def test_request_id_default(self):
        """request_id 默认值为 '-'"""
        assert request_id_var.get("-") == "-"

    def test_user_id_default(self):
        """user_id 默认值为 '-'"""
        assert user_id_var.get("-") == "-"

    def test_request_id_set_get(self):
        """request_id 可以设置和获取"""
        token = request_id_var.set("test-req-123")
        assert request_id_var.get() == "test-req-123"
        request_id_var.reset(token)

    def test_user_id_set_get(self):
        """user_id 可以设置和获取"""
        token = user_id_var.set("user-456")
        assert user_id_var.get() == "user-456"
        user_id_var.reset(token)


class TestLoggerSetup:
    """测试 logger 配置"""

    def test_logger_import(self):
        """logger 可以导入"""
        assert logger is not None

    def test_setup_logger_callable(self):
        """setup_logger 是可调用的"""
        assert callable(setup_logger)

    def test_middleware_import(self):
        """RequestLoggingMiddleware 可以导入"""
        assert RequestLoggingMiddleware is not None

    def test_generate_request_id(self):
        """generate_request_id 返回 8 位字符串"""
        req_id = generate_request_id()
        assert isinstance(req_id, str)
        assert len(req_id) == 8

    def test_generate_request_id_unique(self):
        """generate_request_id 每次生成不同 ID"""
        ids = {generate_request_id() for _ in range(10)}
        assert len(ids) == 10

    def test_get_logger_with_context(self):
        """get_logger_with_context 返回带上下文的 logger"""
        ctx_logger = get_logger_with_context(
            request_id="req-123",
            user_id="user-456",
        )
        assert ctx_logger is not None
