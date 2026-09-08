"""Pydantic Schema 验证单元测试"""
import pytest
from pydantic import ValidationError

from schemas.auth import LoginRequest, ChangePasswordRequest, UpdateMeRequest
from schemas.users import UserCreate
from schemas.chat import ChatRequest


class TestLoginRequestValidation:
    """LoginRequest 验证测试"""

    def test_valid_login(self):
        """有效登录请求"""
        req = LoginRequest(username="zhangsan", password="Password1")
        assert req.username == "zhangsan"
        assert req.password == "Password1"

    def test_empty_username_rejected(self):
        """空用户名被拒绝"""
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="Password1")

    def test_whitespace_only_username_rejected(self):
        """纯空格用户名被拒绝"""
        with pytest.raises(ValidationError):
            LoginRequest(username="   ", password="Password1")

    def test_empty_password_rejected(self):
        """空密码被拒绝"""
        with pytest.raises(ValidationError):
            LoginRequest(username="zhangsan", password="")

    def test_username_stripped(self):
        """用户名自动去首尾空格"""
        req = LoginRequest(username="  zhangsan  ", password="Password1")
        assert req.username == "zhangsan"


class TestChangePasswordValidation:
    """ChangePasswordRequest 验证测试"""

    def test_valid_password(self):
        """有效密码"""
        req = ChangePasswordRequest(old_password="OldPass1", new_password="NewPass123")
        assert req.new_password == "NewPass123"

    def test_short_password_rejected(self):
        """密码太短被拒绝"""
        with pytest.raises(ValidationError):
            ChangePasswordRequest(old_password="OldPass1", new_password="Short1")

    def test_no_uppercase_rejected(self):
        """无大写字母被拒绝"""
        with pytest.raises(ValidationError):
            ChangePasswordRequest(old_password="OldPass1", new_password="lowercase1")

    def test_no_lowercase_rejected(self):
        """无小写字母被拒绝"""
        with pytest.raises(ValidationError):
            ChangePasswordRequest(old_password="OldPass1", new_password="UPPERCASE1")

    def test_no_digit_rejected(self):
        """无数字被拒绝"""
        with pytest.raises(ValidationError):
            ChangePasswordRequest(old_password="OldPass1", new_password="NoDigitsHere")


class TestUpdateMeValidation:
    """UpdateMeRequest 验证测试"""

    def test_valid_name(self):
        """有效昵称"""
        req = UpdateMeRequest(display_name="张三")
        assert req.display_name == "张三"

    def test_empty_name_rejected(self):
        """空昵称被拒绝"""
        with pytest.raises(ValidationError):
            UpdateMeRequest(display_name="")

    def test_whitespace_only_name_rejected(self):
        """纯空格昵称被拒绝"""
        with pytest.raises(ValidationError):
            UpdateMeRequest(display_name="   ")

    def test_xss_chars_rejected(self):
        """XSS 字符被拒绝"""
        with pytest.raises(ValidationError):
            UpdateMeRequest(display_name="<script>alert(1)</script>")

    def test_name_stripped(self):
        """昵称自动去首尾空格"""
        req = UpdateMeRequest(display_name="  张三  ")
        assert req.display_name == "张三"


class TestUserCreateValidation:
    """UserCreate 验证测试"""

    def test_valid_create(self):
        """有效创建请求"""
        req = UserCreate(
            real_name="张三",
            username="zhangsan",
            employee_no="HR001",
            dept_id=1,
            role="employee",
        )
        assert req.real_name == "张三"
        assert req.username == "zhangsan"

    def test_xss_in_real_name_rejected(self):
        """姓名中 XSS 字符被拒绝"""
        with pytest.raises(ValidationError):
            UserCreate(
                real_name="<script>alert(1)</script>",
                username="zhangsan",
                employee_no="HR001",
            )

    def test_invalid_email_rejected(self):
        """无效邮箱被拒绝"""
        with pytest.raises(ValidationError):
            UserCreate(
                real_name="张三",
                username="zhangsan",
                employee_no="HR001",
                email="not-an-email",
            )

    def test_valid_email_accepted(self):
        """有效邮箱被接受"""
        req = UserCreate(
            real_name="张三",
            username="zhangsan",
            employee_no="HR001",
            email="zhangsan@example.com",
        )
        assert req.email == "zhangsan@example.com"

    def test_empty_email_becomes_none(self):
        """空邮箱转为 None"""
        req = UserCreate(
            real_name="张三",
            username="zhangsan",
            employee_no="HR001",
            email="",
        )
        assert req.email is None


class TestChatRequestValidation:
    """ChatRequest 验证测试"""

    def test_valid_query(self):
        """有效查询"""
        req = ChatRequest(query="公司的年假政策是什么？")
        assert req.query == "公司的年假政策是什么？"

    def test_empty_query_rejected(self):
        """空查询被拒绝"""
        with pytest.raises(ValidationError):
            ChatRequest(query="")

    def test_whitespace_only_query_rejected(self):
        """纯空格查询被拒绝"""
        with pytest.raises(ValidationError):
            ChatRequest(query="   ")

    def test_query_stripped(self):
        """查询自动去首尾空格"""
        req = ChatRequest(query="  年假政策  ")
        assert req.query == "年假政策"
