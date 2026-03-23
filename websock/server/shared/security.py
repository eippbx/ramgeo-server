#!/usr/bin/env python3
"""
安全模块
提供认证、授权、加密等安全功能
"""

import hashlib
import hmac
import base64
import secrets
from jose import jwt
import datetime
import uuid
from typing import Dict, Any, Optional
import logging

from shared.logger import setup_logging
from shared.config import Config

logger = setup_logging(__name__)


class SecurityManager:
    """
    安全管理器
    """
    
    def __init__(self, config: Config):
        """
        初始化安全管理器
        
        Args:
            config: 配置管理器实例
        """
        self.config = config
        
        # 加载安全配置
        self.secret_key = config.get('security.secret_key')
        if not self.secret_key:
            raise Exception("缺少必要的配置项: security.secret_key")
        self.jwt_algorithm = config.get('security.jwt_algorithm', 'HS256')
        self.jwt_expiration = config.get('security.jwt_expiration', 3600)  # 1小时
        self.jwt_refresh_expiration = config.get('security.jwt_refresh_expiration', 86400)  # 24小时
        
        # API密钥配置
        self.api_key_length = config.get('security.api_key_length', 32)
        self.api_key_prefix = config.get('security.api_key_prefix', 'ramgeo_')
    
    def generate_api_key(self) -> str:
        """
        生成API密钥
        
        Returns:
            生成的API密钥
        """
        random_bytes = secrets.token_bytes(self.api_key_length)
        api_key = base64.urlsafe_b64encode(random_bytes).decode('utf-8')
        return f"{self.api_key_prefix}{api_key[:self.api_key_length]}"
    
    def hash_api_key(self, api_key: str) -> str:
        """
        哈希API密钥
        
        Args:
            api_key: API密钥
        
        Returns:
            哈希后的API密钥
        """
        hashed = hashlib.sha256(api_key.encode('utf-8')).hexdigest()
        return hashed
    
    def verify_api_key(self, api_key: str, hashed_api_key: str) -> bool:
        """
        验证API密钥
        
        Args:
            api_key: 待验证的API密钥
            hashed_api_key: 存储的哈希API密钥
        
        Returns:
            验证是否通过
        """
        return hmac.compare_digest(self.hash_api_key(api_key), hashed_api_key)
    
    def generate_jwt_token(self, payload: Dict[str, Any], refresh: bool = False) -> str:
        """
        生成JWT令牌
        
        Args:
            payload: JWT载荷
            refresh: 是否为刷新令牌
        
        Returns:
            生成的JWT令牌
        """
        # 添加标准声明
        now = datetime.datetime.utcnow()
        
        if refresh:
            expiration = now + datetime.timedelta(seconds=self.jwt_refresh_expiration)
            token_type = 'refresh'
        else:
            expiration = now + datetime.timedelta(seconds=self.jwt_expiration)
            token_type = 'access'
        
        token_payload = {
            'iss': 'ramgeo-distributed-system',
            'iat': now,
            'exp': expiration,
            'jti': str(uuid.uuid4()),
            'token_type': token_type,
            **payload
        }
        
        # 生成令牌
        token = jwt.encode(token_payload, self.secret_key, algorithm=self.jwt_algorithm)
        
        return token
    
    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证JWT令牌
        
        Args:
            token: JWT令牌
        
        Returns:
            解码后的载荷或None
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT令牌已过期")
            return None
        except jwt.InvalidTokenError:
            logger.warning("无效的JWT令牌")
            return None
    
    def refresh_jwt_token(self, refresh_token: str) -> Optional[str]:
        """
        使用刷新令牌获取新的访问令牌
        
        Args:
            refresh_token: 刷新令牌
        
        Returns:
            新的访问令牌或None
        """
        payload = self.verify_jwt_token(refresh_token)
        
        if not payload:
            return None
        
        # 检查是否为刷新令牌
        if payload.get('token_type') != 'refresh':
            logger.warning("无效的刷新令牌类型")
            return None
        
        # 移除过期时间和令牌类型，生成新的访问令牌
        payload.pop('exp', None)
        payload.pop('token_type', None)
        
        return self.generate_jwt_token(payload)
    
    def encrypt_data(self, data: str) -> str:
        """
        加密数据
        
        Args:
            data: 待加密的数据
        
        Returns:
            加密后的数据
        """
        # 使用AES-GCM加密
        import cryptography
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        
        try:
            # 生成随机密钥和IV
            key = hashlib.sha256(self.secret_key.encode('utf-8')).digest()
            iv = secrets.token_bytes(12)  # AES-GCM需要12字节IV
            
            # 创建加密器
            cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
            encryptor = cipher.encryptor()
            
            # 加密数据
            ciphertext = encryptor.update(data.encode('utf-8')) + encryptor.finalize()
            
            # 组合IV、密文和认证标签
            encrypted_data = iv + encryptor.tag + ciphertext
            
            # 编码为base64
            return base64.urlsafe_b64encode(encrypted_data).decode('utf-8')
            
        except ImportError:
            logger.error("cryptography库未安装，无法使用加密功能")
            return data  # 回退到原始数据
        except Exception as e:
            logger.error(f"加密数据失败: {e}")
            return data
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """
        解密数据
        
        Args:
            encrypted_data: 加密后的数据
        
        Returns:
            解密后的数据
        """
        # 使用AES-GCM解密
        import cryptography
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        
        try:
            # 解码base64
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data)
            
            # 提取IV、标签和密文
            iv = encrypted_bytes[:12]
            tag = encrypted_bytes[12:28]
            ciphertext = encrypted_bytes[28:]
            
            # 生成密钥
            key = hashlib.sha256(self.secret_key.encode('utf-8')).digest()
            
            # 创建解密器
            cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
            decryptor = cipher.decryptor()
            
            # 解密数据
            decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            return decrypted_data.decode('utf-8')
            
        except ImportError:
            logger.error("cryptography库未安装，无法使用解密功能")
            return encrypted_data  # 回退到原始数据
        except Exception as e:
            logger.error(f"解密数据失败: {e}")
            return encrypted_data
    
    def generate_hash(self, data: str) -> str:
        """
        生成数据的哈希值
        
        Args:
            data: 待哈希的数据
        
        Returns:
            哈希值
        """
        return hashlib.sha256(data.encode('utf-8')).hexdigest()
    
    def verify_hash(self, data: str, hashed_data: str) -> bool:
        """
        验证数据的哈希值
        
        Args:
            data: 待验证的数据
            hashed_data: 存储的哈希值
        
        Returns:
            验证是否通过
        """
        return hmac.compare_digest(self.generate_hash(data), hashed_data)
    
    def generate_signature(self, data: str, timestamp: str) -> str:
        """
        生成数据签名
        
        Args:
            data: 待签名的数据
            timestamp: 时间戳
        
        Returns:
            生成的签名
        """
        message = f"{data}{timestamp}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def verify_signature(self, data: str, timestamp: str, signature: str) -> bool:
        """
        验证数据签名
        
        Args:
            data: 原始数据
            timestamp: 时间戳
            signature: 待验证的签名
        
        Returns:
            验证是否通过
        """
        expected_signature = self.generate_signature(data, timestamp)
        return hmac.compare_digest(expected_signature, signature)
    
    def sanitize_input(self, input_data: str) -> str:
        """
        清理输入数据，防止注入攻击
        
        Args:
            input_data: 输入数据
        
        Returns:
            清理后的输入数据
        """
        # 简单的输入清理
        import re
        
        # 移除可能的脚本标签
        sanitized = re.sub(r'<script[^>]*>(.*?)<\/script>', '', input_data, flags=re.IGNORECASE | re.DOTALL)
        
        # 转义HTML特殊字符
        sanitized = sanitized.replace('&', '&amp;')
        sanitized = sanitized.replace('<', '&lt;')
        sanitized = sanitized.replace('>', '&gt;')
        sanitized = sanitized.replace('"', '&quot;')
        sanitized = sanitized.replace("'", '&#x27;')
        
        return sanitized
    
    def validate_ip_address(self, ip_address: str) -> bool:
        """
        验证IP地址格式
        
        Args:
            ip_address: IP地址
        
        Returns:
            格式是否有效
        """
        import re
        
        # 简单的IPv4和IPv6验证
        ipv4_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        ipv6_pattern = r'^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$'
        
        return bool(re.match(ipv4_pattern, ip_address) or re.match(ipv6_pattern, ip_address))
    
    def generate_uuid(self) -> str:
        """
        生成UUID
        
        Returns:
            UUID字符串
        """
        return str(uuid.uuid4())
