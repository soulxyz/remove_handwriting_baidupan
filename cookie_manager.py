"""
Cookie持久化管理
"""
import json
import os
from typing import Dict, Optional
from datetime import datetime


class CookieManager:
    """管理和持久化cookies"""
    
    def __init__(self, cookie_file: str = "plusai_cookies.json"):
        """
        初始化Cookie管理器
        
        Args:
            cookie_file: Cookie保存文件路径
        """
        self.cookie_file = cookie_file
    
    def save_cookies(self, cookies: Dict[str, str], username: str = "default") -> bool:
        """
        保存cookies到文件
        
        Args:
            cookies: cookies字典
            username: 用户名（用于区分不同账号的cookies）
            
        Returns:
            bool: 是否保存成功
        """
        try:
            # 读取现有数据
            data = {}
            if os.path.exists(self.cookie_file):
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            
            # 添加新的cookies
            data[username] = {
                'cookies': cookies,
                'saved_at': datetime.now().isoformat(),
                'expires': self._get_expiry_time(cookies)
            }
            
            # 保存到文件
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"保存cookies失败: {e}")
            return False
    
    def load_cookies(self, username: str = "default") -> Optional[Dict[str, str]]:
        """
        从文件加载cookies
        
        Args:
            username: 用户名
            
        Returns:
            Dict或None: cookies字典，如果不存在或已过期返回None
        """
        try:
            if not os.path.exists(self.cookie_file):
                return None
            
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if username not in data:
                return None
            
            user_data = data[username]
            
            # 检查是否过期
            if self._is_expired(user_data):
                print(f"Cookies已过期，需要重新登录")
                return None
            
            print(f"✅ 加载了保存的cookies（保存于{user_data['saved_at'][:10]}）")
            return user_data['cookies']
            
        except Exception as e:
            print(f"加载cookies失败: {e}")
            return None
    
    def clear_cookies(self, username: str = "default") -> bool:
        """
        清除指定用户的cookies
        
        Args:
            username: 用户名
            
        Returns:
            bool: 是否成功
        """
        try:
            if not os.path.exists(self.cookie_file):
                return True
            
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if username in data:
                del data[username]
                
                with open(self.cookie_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"清除cookies失败: {e}")
            return False
    
    def _get_expiry_time(self, cookies: Dict[str, str]) -> Optional[str]:
        """
        从JWT token中提取过期时间
        
        Args:
            cookies: cookies字典
            
        Returns:
            过期时间字符串
        """
        try:
            import base64
            
            # 尝试从auth_token提取
            auth_token = cookies.get('__Secure-auth_token', '')
            if auth_token:
                # JWT格式: header.payload.signature
                parts = auth_token.split('.')
                if len(parts) >= 2:
                    # 解码payload（需要添加padding）
                    payload = parts[1]
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += '=' * padding
                    
                    decoded = base64.urlsafe_b64decode(payload)
                    payload_data = json.loads(decoded)
                    
                    exp_timestamp = payload_data.get('exp')
                    if exp_timestamp:
                        from datetime import datetime
                        exp_time = datetime.fromtimestamp(exp_timestamp)
                        return exp_time.isoformat()
            
            return None
        except:
            return None
    
    def _is_expired(self, user_data: Dict) -> bool:
        """
        检查cookies是否过期
        
        Args:
            user_data: 用户数据
            
        Returns:
            bool: 是否过期
        """
        try:
            expires = user_data.get('expires')
            if not expires:
                # 如果没有过期时间，检查保存时间
                saved_at = user_data.get('saved_at')
                if saved_at:
                    from datetime import datetime, timedelta
                    saved_time = datetime.fromisoformat(saved_at)
                    # 如果保存超过12小时，认为可能过期
                    if datetime.now() - saved_time > timedelta(hours=12):
                        return True
                return False
            
            from datetime import datetime
            exp_time = datetime.fromisoformat(expires)
            return datetime.now() >= exp_time
            
        except:
            return False

