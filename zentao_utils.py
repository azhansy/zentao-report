#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
禅道集成模块 - 通用工具函数
提供所有 zentao 脚本共用的工具函数
"""

import requests
import json
import subprocess
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import unicodedata
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from zentao_config import (
    DISPLAY_CONFIG,
    ZENTAO_CONFIG,
    FEISHU_CONFIG,
)


_REQUESTS_SESSION = None


def _get_requests_session() -> requests.Session:
    """Get a shared requests session with retry policy."""
    global _REQUESTS_SESSION
    if _REQUESTS_SESSION is None:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _REQUESTS_SESSION = session
    return _REQUESTS_SESSION


def request_json(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict] = None,
    json_body: Optional[Dict] = None,
    timeout: int = 15,
    max_retries: int = 3,
    backoff: float = 1.0,
) -> Optional[Dict]:
    """Send a request and parse JSON with basic retries."""
    session = _get_requests_session()
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=timeout,
            )
            if resp.status_code != 200:
                print(f"❌ 请求失败: {resp.status_code} - {resp.text[:200]}")
                return None
            try:
                return resp.json()
            except requests.exceptions.JSONDecodeError as e:
                print(f"❌ JSON 解析失败: {e}")
                print(f"响应内容: {resp.text[:200]}")
                return None
        except requests.exceptions.SSLError as e:
            print(f"⚠️  SSL 错误 (第 {attempt}/{max_retries} 次): {e}")
            if attempt == max_retries:
                return None
            time.sleep(backoff * attempt)
        except requests.RequestException as e:
            print(f"⚠️  网络请求异常 (第 {attempt}/{max_retries} 次): {e}")
            if attempt == max_retries:
                return None
            time.sleep(backoff * attempt)
    return None


# ==================== Token 缓存配置 ====================

# Token 缓存文件路径：优先使用当前工作目录，便于多项目管理
# 如果当前目录不可写，则使用用户主目录
def get_token_cache_path() -> Path:
    """获取 token 缓存文件路径"""
    # 优先使用当前工作目录
    cwd_cache = Path.cwd() / ".zentao_token_cache"
    try:
        # 测试是否可写
        cwd_cache.touch(exist_ok=True)
        return cwd_cache
    except (PermissionError, OSError):
        # 如果当前目录不可写，使用用户主目录
        return Path.home() / ".zentao_token_cache"

TOKEN_EXPIRE_HOURS = 24  # Token 有效期（小时）


def load_cached_token() -> Optional[Dict]:
    """
    加载缓存的 token
    
    Returns:
        包含 token 和 timestamp 的字典，失败返回 None
    """
    try:
        cache_file = get_token_cache_path()
        if not cache_file.exists():
            return None
        
        with open(cache_file, 'r') as f:
            cache = json.load(f)
        
        # 检查 token 是否过期
        timestamp = datetime.fromisoformat(cache.get('timestamp', ''))
        now = datetime.now()
        
        if now - timestamp > timedelta(hours=TOKEN_EXPIRE_HOURS):
            print("⏰ Token 已过期，需要重新登录")
            return None
        
        return cache
    except Exception as e:
        print(f"⚠️  读取 token 缓存失败: {e}")
        return None


def save_token_cache(token: str):
    """
    保存 token 到缓存文件
    
    Args:
        token: 禅道 token
    """
    try:
        cache_file = get_token_cache_path()
        cache = {
            'token': token,
            'timestamp': datetime.now().isoformat()
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache, f, indent=2)
        
        print(f"💾 Token 已缓存（有效期 {TOKEN_EXPIRE_HOURS} 小时）")
    except Exception as e:
        print(f"⚠️  保存 token 缓存失败: {e}")


def verify_token(token: str) -> bool:
    """
    验证 token 是否有效
    
    Args:
        token: 禅道 token
    
    Returns:
        True 表示有效，False 表示无效
    """
    try:
        # 使用一个简单的 API 调用来验证 token
        url = f"{ZENTAO_CONFIG['base_url']}/users"
        headers = {'Token': token}
        
        resp = requests.get(url, headers=headers, timeout=5)
        
        if resp.status_code == 200:
            return True
        else:
            return False
    except Exception:
        return False


# ==================== 禅道 API ====================

def login_zentao(use_curl: bool = False, force_refresh: bool = False) -> Optional[str]:
    """
    登录禅道获取 token（支持缓存）
    
    Args:
        use_curl: 是否使用 curl 命令行工具（用于绕过 WAF）
        force_refresh: 是否强制刷新 token，忽略缓存
    
    Returns:
        token 字符串，失败返回 None
    """
    # 如果不是强制刷新，先尝试使用缓存的 token
    if not force_refresh:
        cached = load_cached_token()
        if cached:
            token = cached.get('token')
            if token:
                # 验证 token 是否仍然有效
                if verify_token(token):
                    print("✅ 使用缓存的 token")
                    return token
                else:
                    print("⚠️  缓存的 token 已失效，重新登录")
    
    # 缓存不存在或已失效，执行登录
    """
    登录禅道获取 token
    
    Args:
        use_curl: 是否使用 curl 命令行工具（用于绕过 WAF）
    
    Returns:
        token 字符串，失败返回 None
    """
    url = f"{ZENTAO_CONFIG['base_url']}/tokens"
    payload = {
        "account": ZENTAO_CONFIG['username'],
        "password": ZENTAO_CONFIG['password']
    }
    
    if use_curl:
        # 使用 curl 绕过 WAF
        try:
            cmd = [
                'curl', '-sS', '-L',
                '--connect-timeout', '10',
                '--max-time', '30',
                '--retry', '2',
                '--retry-delay', '1',
                '-X', 'POST', url,
                '-H', 'Content-Type: application/json',
                '-d', json.dumps(payload),
                '-w', '\n%{http_code}'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            
            if result.returncode != 0:
                error_text = (result.stderr or result.stdout or '').strip()
                if error_text:
                    print(f"❌ curl 执行失败（退出码 {result.returncode}）: {error_text}")
                else:
                    print(f"❌ curl 执行失败（退出码 {result.returncode}），无错误输出")
                return None
            
            output = result.stdout.rstrip('\n')
            response_text, _, status_code = output.rpartition('\n')
            response_text = response_text.strip()
            status_code = status_code.strip()
            if status_code and status_code != '200':
                print(f"❌ HTTP 错误: {status_code}")
                print(f"   响应内容: {response_text[:200]}")
                return None
            if not response_text:
                print("❌ 登录响应为空")
                return None

            resp_json = json.loads(response_text)
            token = resp_json.get("token")
            
            if token:
                print("✅ 登录成功（使用 curl）")
                save_token_cache(token)  # 保存到缓存
                return token
            else:
                print(f"❌ 响应中没有 token: {response_text}")
                return None
                
        except subprocess.TimeoutExpired:
            print("❌ 请求超时")
            return None
        except Exception as e:
            print(f"❌ 登录出错: {e}")
            return None
    else:
        # 使用 requests 库
        try:
            resp = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
            
            # 检查 HTTP 状态码
            if resp.status_code != 200:
                print(f"❌ HTTP 错误: {resp.status_code}")
                print(f"   响应内容: {resp.text[:200]}")
                return None
            
            # 尝试解析 JSON
            try:
                resp_json = resp.json()
            except json.JSONDecodeError as je:
                print(f"❌ JSON 解析失败: {je}")
                print(f"   响应内容: {resp.text[:200]}")
                print(f"   提示: 可能被 WAF 拦截，尝试使用 login_zentao(use_curl=True)")
                return None
            
            token = resp_json.get("token")
            
            if token:
                print("✅ 登录成功")
                save_token_cache(token)  # 保存到缓存
                return token
            else:
                print(f"❌ 登录失败: {resp_json}")
                return None
                
        except requests.Timeout:
            print("❌ 请求超时")
            return None
        except requests.RequestException as e:
            print(f"❌ 网络请求出错: {e}")
            return None
        except Exception as e:
            print(f"❌ 登录出错: {e}")
            return None


def get_zentao_headers(token: str) -> Dict[str, str]:
    """
    获取禅道 API 请求头
    
    Args:
        token: 登录 token
    
    Returns:
        请求头字典
    """
    return {'Token': token}


def get_task_web_url(task_id: int) -> str:
    """
    获取任务的 Web 链接
    
    Args:
        task_id: 任务 ID
    
    Returns:
        任务的 Web 链接
    """
    return f"{ZENTAO_CONFIG['web_url']}/task-view-{task_id}.html"


def get_bug_web_url(bug_id: int) -> str:
    """
    获取 Bug 的 Web 链接
    
    Args:
        bug_id: Bug ID
    
    Returns:
        Bug 的 Web 链接
    """
    return f"{ZENTAO_CONFIG['web_url']}/bug-view-{bug_id}.html"


# ==================== 时间工具 ====================

def get_current_week() -> Tuple[datetime, datetime]:
    """
    获取本周的开始和结束时间（周一 00:00:00 到周日 23:59:59）
    
    Returns:
        (本周一, 本周日) 元组
    """
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def get_last_week() -> Tuple[datetime, datetime]:
    """
    获取上周的开始和结束时间（上周一 00:00:00 到上周日 23:59:59）
    
    Returns:
        (上周一, 上周日) 元组
    """
    today = datetime.now()
    last_monday = (today - timedelta(days=today.weekday() + 7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    last_sunday = last_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return last_monday, last_sunday


def get_current_month() -> Tuple[datetime, datetime]:
    """
    获取本月的开始和结束时间（1号 00:00:00 到最后一天 23:59:59）
    
    Returns:
        (本月第一天, 本月最后一天) 元组
    """
    today = datetime.now()
    # 本月第一天
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # 下月第一天
    if today.month == 12:
        first_day_next_month = today.replace(
            year=today.year + 1, month=1, day=1, 
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        first_day_next_month = today.replace(
            month=today.month + 1, day=1, 
            hour=0, minute=0, second=0, microsecond=0
        )
    # 本月最后一天
    last_day = first_day_next_month - timedelta(seconds=1)
    return first_day, last_day


def parse_zentao_datetime(date_str: str) -> Optional[datetime]:
    """
    解析禅道的日期时间字符串
    
    Args:
        date_str: 日期时间字符串，格式如 "2025-12-12T10:30:00Z"
    
    Returns:
        datetime 对象，解析失败返回 None
    """
    if not date_str:
        return None
    
    try:
        # 去掉 T 和 Z
        date_str = date_str.replace("T", " ").replace("Z", "")
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except:
        try:
            # 尝试其他格式
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        except:
            return None


# ==================== 飞书通知 ====================

def send_feishu_message(payload: Dict, webhook: Optional[str] = None) -> bool:
    """
    发送飞书消息
    
    Args:
        payload: 飞书消息 payload
        webhook: 飞书 webhook 地址，默认使用配置中的
    
    Returns:
        True 表示发送成功
    """
    webhook_url = webhook or FEISHU_CONFIG['webhook']
    
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            if result.get('code') == 0:
                print("✅ 飞书消息发送成功")
                return True
            else:
                print(f"❌ 飞书消息发送失败: {result}")
                return False
        else:
            print(f"❌ 飞书消息发送失败，状态码: {resp.status_code}，响应: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ 发送飞书消息时出错: {e}")
        return False


def create_feishu_post_message(title: str, content: List[List[Dict]], 
                               zh_cn: bool = True) -> Dict:
    """
    创建飞书 post 格式消息
    
    Args:
        title: 消息标题
        content: 消息内容，格式为 [[{"tag": "text", "text": "..."}], ...]
        zh_cn: 是否使用中文
    
    Returns:
        飞书消息 payload
    """
    lang = "zh_cn" if zh_cn else "en_us"
    
    return {
        "msg_type": "post",
        "content": {
            "post": {
                lang: {
                    "title": title,
                    "content": content
                }
            }
        }
    }


def create_feishu_text_message(text: str) -> Dict:
    """
    创建飞书 text 格式消息
    
    Args:
        text: 消息文本
    
    Returns:
        飞书消息 payload
    """
    return {
        "msg_type": "text",
        "content": {
            "text": text
        }
    }


# ==================== 文本格式化 ====================

def pad_text(text: str, width: Optional[int] = None) -> str:
    """
    填充文本到指定宽度（考虑中文字符宽度）
    
    Args:
        text: 要填充的文本
        width: 目标宽度，默认使用配置中的固定宽度
    
    Returns:
        填充后的文本
    """
    if width is None:
        width = DISPLAY_CONFIG['fixed_user_width']
    
    # 计算文本的实际显示宽度（中文字符算2个宽度）
    display_width = sum(
        2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 
        for c in text
    )
    
    # 计算需要填充的空格数
    padding = max(width - display_width, 0)
    return text + " " * padding


def format_date(dt: datetime) -> str:
    """
    格式化日期
    
    Args:
        dt: datetime 对象
    
    Returns:
        格式化后的日期字符串
    """
    return dt.strftime(DISPLAY_CONFIG['date_format'])


def format_datetime(dt: datetime) -> str:
    """
    格式化日期时间
    
    Args:
        dt: datetime 对象
    
    Returns:
        格式化后的日期时间字符串
    """
    return dt.strftime(DISPLAY_CONFIG['datetime_format'])


# ==================== 数据提取 ====================

def extract_user_info(user_dict: Optional[Dict]) -> Tuple[str, str]:
    """
    从禅道用户字典中提取账号和真实姓名
    
    Args:
        user_dict: 禅道用户字典，如 {"account": "todd", "realname": "TC"}
    
    Returns:
        (account, realname) 元组，如果信息不存在则返回空字符串
    """
    if not user_dict or not isinstance(user_dict, dict):
        return "", ""
    
    account = user_dict.get("account", "")
    realname = user_dict.get("realname", "")
    
    # 如果 realname 是数字，忽略它
    if realname and realname.isdigit():
        realname = ""
    
    return account, realname


def build_account_to_realname_map(tasks: List[Dict]) -> Dict[str, str]:
    """
    从任务列表中构建 account -> realname 映射表
    
    Args:
        tasks: 任务列表
    
    Returns:
        account -> realname 映射字典
    """
    mapping = {}
    
    for task in tasks:
        # 从 assignedTo 提取
        assigned = task.get("assignedTo")
        if assigned and isinstance(assigned, dict):
            account, realname = extract_user_info(assigned)
            if account and realname:
                mapping[account] = realname
        
        # 从 team 提取
        team = task.get("team", [])
        if isinstance(team, list):
            for member in team:
                account, realname = extract_user_info(member)
                if account and realname:
                    mapping[account] = realname
    
    return mapping


# ==================== 测试函数 ====================

def test_zentao_connection() -> bool:
    """
    测试禅道连接
    
    Returns:
        True 表示连接成功
    """
    print("=" * 60)
    print("测试禅道连接")
    print("=" * 60)
    
    token = login_zentao()
    if token:
        print(f"✅ 成功获取 token: {token[:20]}...")
        return True
    else:
        print("❌ 无法获取 token")
        return False


def test_feishu_webhook() -> bool:
    """
    测试飞书 webhook
    
    Returns:
        True 表示测试成功
    """
    print("=" * 60)
    print("测试飞书 Webhook")
    print("=" * 60)
    
    payload = create_feishu_text_message("🧪 这是一条测试消息")
    return send_feishu_message(payload)


if __name__ == '__main__':
    """工具函数测试"""
    
    # 测试禅道连接
    test_zentao_connection()
    
    print()
    
    # 测试时间工具
    print("=" * 60)
    print("时间工具测试")
    print("=" * 60)
    monday, sunday = get_current_week()
    print(f"本周: {format_date(monday)} ~ {format_date(sunday)}")
    
    first_day, last_day = get_current_month()
    print(f"本月: {format_date(first_day)} ~ {format_date(last_day)}")
    
    print()
    
    # 测试文本格式化
    print("=" * 60)
    print("文本格式化测试")
    print("=" * 60)
    print(f"'{pad_text('TC', 12)}' (宽度12)")
    print(f"'{pad_text('小琛', 12)}' (宽度12)")
    print(f"'{pad_text('健华', 12)}' (宽度12)")
    
    print()
    
    # 询问是否测试飞书
    response = input("是否测试飞书 Webhook？(y/n): ")
    if response.lower() == 'y':
        test_feishu_webhook()
