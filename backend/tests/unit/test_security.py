"""
安全模块单元测试

测试范围：密码哈希、JWT 生成/验证
对应 API 文档：认证模块基础功能
"""

import pytest
from core.security import hash_password, verify_password, create_access_token, decode_token


class TestPasswordHashing:
    """密码哈希测试"""

    @pytest.mark.unit
    def test_password_hashed_correctly(self):
        """验证密码正确哈希"""
        password = "SecurePassword@123"
        hashed = hash_password(password)

        assert hashed != password
        assert verify_password(password, hashed)

    @pytest.mark.unit
    def test_wrong_password_fails(self):
        """错误密码应验证失败"""
        password = "SecurePassword@123"
        hashed = hash_password(password)

        assert not verify_password("WrongPassword", hashed)

    @pytest.mark.unit
    def test_different_passwords_different_hashes(self):
        """不同密码生成不同哈希"""
        hash1 = hash_password("Password@123")
        hash2 = hash_password("Password@456")

        assert hash1 != hash2

    @pytest.mark.unit
    def test_same_password_multiple_verifications(self):
        """相同密码应通过多次验证"""
        password = "TestPassword@123"
        hashed = hash_password(password)

        for _ in range(5):
            assert verify_password(password, hashed)

    @pytest.mark.unit
    def test_password_case_sensitive(self):
        """密码大小写敏感"""
        password = "Password@123"
        hashed = hash_password(password)

        assert verify_password(password, hashed)
        assert not verify_password("password@123", hashed)
        assert not verify_password("PASSWORD@123", hashed)

    @pytest.mark.unit
    def test_empty_password_can_be_hashed(self):
        """空字符串也可以被哈希"""
        hashed = hash_password("")
        assert hashed != ""
        assert verify_password("", hashed)


class TestJWTToken:
    """JWT Token 测试"""

    @pytest.mark.unit
    def test_token_creation(self):
        """验证 Token 创建"""
        token, jti, expires_at = create_access_token(user_id=1, role="employee")

        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT 三段结构

    @pytest.mark.unit
    def test_token_includes_required_claims(self):
        """验证 Token 包含必要的声明"""
        token, jti, expires_at = create_access_token(user_id=123, role="employee")

        decoded = decode_token(token)

        assert decoded["sub"] == "123"
        assert decoded["role"] == "employee"
        assert "exp" in decoded
        assert "iat" in decoded
        assert "jti" in decoded
        assert decoded["jti"] == jti

    @pytest.mark.unit
    def test_different_users_different_tokens(self):
        """不同用户生成不同 Token"""
        token1, jti1, _ = create_access_token(user_id=1, role="employee")
        token2, jti2, _ = create_access_token(user_id=2, role="admin")

        assert token1 != token2
        assert jti1 != jti2

    @pytest.mark.unit
    def test_token_with_different_roles(self):
        """验证不同角色的 Token 包含正确的 role"""
        for role in ["employee", "dept_admin", "super_admin"]:
            token, jti, _ = create_access_token(user_id=1, role=role)
            decoded = decode_token(token)
            assert decoded["role"] == role

    @pytest.mark.unit
    def test_token_jti_uniqueness(self):
        """同一用户多次生成 Token，jti 应不同"""
        import time

        token1, jti1, _ = create_access_token(user_id=1, role="employee")
        time.sleep(0.01)
        token2, jti2, _ = create_access_token(user_id=1, role="employee")

        assert token1 != token2
        assert jti1 != jti2

    @pytest.mark.unit
    def test_decode_token_valid(self):
        """验证有效 Token 可以正确解码"""
        token, jti, _ = create_access_token(user_id=42, role="dept_admin")
        decoded = decode_token(token)

        assert decoded["sub"] == "42"
        assert decoded["role"] == "dept_admin"

    @pytest.mark.unit
    def test_decode_token_invalid(self):
        """验证无效 Token 解码失败"""
        with pytest.raises(Exception):
            decode_token("invalid.token.here")

    @pytest.mark.unit
    def test_decode_token_expired(self):
        """验证过期 Token 解码失败"""
        from tests.utils import create_expired_token

        expired_token = create_expired_token(user_id=1, hours=-1)

        with pytest.raises(Exception):
            decode_token(expired_token)
