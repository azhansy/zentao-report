#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
禅道集成模块统一配置文件
所有 zentao 相关脚本都应该从这里导入配置
"""

import configparser
import json
import os
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# ==================== 加载外部配置文件 ====================

def _load_config():
    """加载外部配置文件，优先级：当前目录 > 可执行文件目录 > 用户主目录"""
    config = configparser.ConfigParser()
    
    # 查找配置文件的可能位置
    possible_paths = [
        Path.cwd() / 'zentao.ini',                    # 当前工作目录
        Path(__file__).parent / 'zentao.ini',         # 脚本所在目录（开发模式）
        Path(os.path.abspath(__file__)).parent / 'zentao.ini',  # 绝对路径
        Path.home() / '.zentao.ini',                  # 用户主目录
    ]
    
    # 如果是打包后的可执行文件，添加可执行文件目录
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        possible_paths.insert(0, exe_dir / 'zentao.ini')
    
    config_path = None
    for path in possible_paths:
        if path.exists():
            config_path = path
            break
    
    if not config_path:
        raise FileNotFoundError(
            f"❌ 找不到配置文件 zentao.ini\n"
            f"请在以下任一位置创建配置文件：\n" +
            '\n'.join(f"  - {p}" for p in possible_paths[:3])
        )
    
    config.read(config_path, encoding='utf-8')
    print(f"✅ 已加载配置文件: {config_path}")
    return config

import sys
_config = _load_config()

# ==================== 禅道基础配置 ====================

# 禅道 API 配置
ZENTAO_CONFIG = {
    'base_url': _config.get('zentao', 'base_url'),
    'web_url': _config.get('zentao', 'web_url'),
    'username': _config.get('zentao', 'username'),
    'password': _config.get('zentao', 'password'),
}

# 项目和产品配置
PROJECT_CONFIG = {
    'project_id': _config.getint('project', 'project_id', fallback=0),
    'product_id': _config.getint('project', 'product_id', fallback=0),
}

# API 分页配置
API_CONFIG = {
    'page': _config.getint('api', 'page'),
    'limit': _config.getint('api', 'limit'),
}

# ==================== 飞书配置 ====================

# 飞书 Webhook 配置（从外部文件读取）
FEISHU_CONFIG = {
    'webhook': _config.get('feishu', 'webhook', fallback='').strip(),
}


def _parse_target_key(raw_key: str) -> Optional[Tuple[int, int]]:
    """Parse mapping key to (project_id, product_id)."""
    key = raw_key.strip()
    for sep in ('_', ','):
        if sep in key:
            left, right = key.split(sep, 1)
            left, right = left.strip(), right.strip()
            if left.isdigit() and right.isdigit():
                return int(left), int(right)
            return None
    return None


def _build_project_product_targets() -> List[Dict[str, object]]:
    """Build notification targets from config mapping, fallback to single target."""
    targets: List[Dict[str, object]] = []

    # New mode: [project_webhook_map] with key format projectId_productId
    # Example:
    # [project_webhook_map]
    # 2_1 = https://open.feishu.cn/open-apis/bot/v2/hook/xxx
    if _config.has_section('project_webhook_map'):
        for key, webhook in _config.items('project_webhook_map'):
            parsed = _parse_target_key(key)
            if not parsed:
                print(f"⚠️  忽略非法 project_webhook_map 键: {key}")
                continue

            project_id, product_id = parsed
            webhook = webhook.strip()
            if not webhook:
                print(f"⚠️  忽略空 webhook 映射: {key}")
                continue

            targets.append({
                'project_id': project_id,
                'product_id': product_id,
                'webhook': webhook,
            })

    # Backward compatible fallback: single [project] + [feishu].webhook
    if not targets:
        project_id = _config.getint('project', 'project_id', fallback=0)
        product_id = _config.getint('project', 'product_id', fallback=0)
        webhook = _config.get('feishu', 'webhook', fallback='').strip()

        if not project_id or not product_id or not webhook:
            raise ValueError(
                "❌ 配置缺失：请配置 [project_webhook_map]，或提供 [project] + [feishu].webhook"
            )

        targets.append({
            'project_id': project_id,
            'product_id': product_id,
            'webhook': webhook,
        })

    return targets


PROJECT_PRODUCT_TARGETS = _build_project_product_targets()

# If [project] is absent, keep backward-compatible defaults from the first target.
if not PROJECT_CONFIG['project_id'] or not PROJECT_CONFIG['product_id']:
    PROJECT_CONFIG = {
        'project_id': PROJECT_PRODUCT_TARGETS[0]['project_id'],
        'product_id': PROJECT_PRODUCT_TARGETS[0]['product_id'],
    }

# Quick lookup map: (project_id, product_id) -> webhook
PROJECT_WEBHOOK_MAP = {
    (target['project_id'], target['product_id']): target['webhook']
    for target in PROJECT_PRODUCT_TARGETS
}


def get_target_webhook(project_id: int, product_id: int) -> str:
    """Get webhook for a project/product pair, fallback to default webhook."""
    return PROJECT_WEBHOOK_MAP.get((project_id, product_id), FEISHU_CONFIG['webhook'])

# ==================== 用户配置（统一管理）====================

# 用户信息建议放到 users.json（本地文件，不提交）
# 读取优先级：
# 1. 环境变量 ZENTAO_USERS_FILE
# 2. 当前工作目录 users.json
# 3. 脚本目录 users.json
# 4. 用户目录 ~/.zentao_users.json
def _normalize_user_config(users: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}

    for account, user in users.items():
        if not isinstance(user, dict):
            continue

        display_name = str(user.get('display_name', account)).strip() or account
        feishu_id = str(user.get('feishu_id', '')).strip()
        variants = user.get('name_variants')
        if not isinstance(variants, list) or not variants:
            variants = [display_name, account]

        normalized[account] = {
            'display_name': display_name,
            'feishu_id': feishu_id,
            'name_variants': [str(v) for v in variants if str(v).strip()],
            'is_tester': bool(user.get('is_tester', False)),
            'exclude': bool(user.get('exclude', False)),
        }

    return normalized


def _load_users() -> Dict[str, Dict[str, Any]]:
    env_path = os.getenv('ZENTAO_USERS_FILE', '').strip()
    possible_paths: List[Path] = []

    if env_path:
        possible_paths.append(Path(env_path).expanduser())

    possible_paths.extend([
        Path.cwd() / 'users.json',
        Path(__file__).parent / 'users.json',
        Path.home() / '.zentao_users.json',
    ])

    for path in possible_paths:
        if not path.exists():
            continue

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                print(f"⚠️  用户配置格式非法，已忽略: {path}")
                continue

            users = _normalize_user_config(data)
            print(f"✅ 已加载用户映射文件: {path}")
            return users
        except Exception as e:
            print(f"⚠️  读取用户映射失败，已忽略 {path}: {e}")

    print("⚠️  未找到 users.json，使用空用户映射（将不进行人员@提醒映射）")
    return {}


USERS = _load_users()

# ==================== 从统一配置生成映射表（向后兼容）====================

# 禅道用户名 -> 飞书用户 open_id 映射表
ZENTAO_FEISHU_USER_MAP = {
    account: user['feishu_id'] 
    for account, user in USERS.items()
}

# 禅道用户名 -> 显示名称映射
ZENTAO_USER_DISPLAY_NAME = {
    account: user['display_name'] 
    for account, user in USERS.items()
}

# 名称变体 -> 标准账号映射
ZENTAO_NAME_VARIANTS = {}
for account, user in USERS.items():
    for variant in user['name_variants']:
        ZENTAO_NAME_VARIANTS[variant] = account

# ==================== 角色配置 ====================

# 测试人员列表
TESTER_ACCOUNTS = [
    account for account, user in USERS.items() 
    if user.get('is_tester', False)
]

# 排除的用户列表
EXCLUDE_USERS = [
    account for account, user in USERS.items() 
    if user.get('exclude', False)
]

# ==================== 显示配置 ====================

# UI 显示配置（从外部文件读取）
DISPLAY_CONFIG = {
    'fixed_user_width': _config.getint('display', 'fixed_user_width', fallback=12),
    'date_format': '%Y-%m-%d',
    'datetime_format': '%Y-%m-%d %H:%M:%S',
}

# 任务状态图标映射
TASK_STATUS_ICONS = {
    'done': '✅',
    'doing': '🔄',
    'wait': '⏸️',
    'assigned': '📌',
    'closed': '✅',
    'cancel': '❌',
    'pause': '⏸️',
}

# Bug 状态图标映射
BUG_STATUS_ICONS = {
    'active': '🐞',
    'resolved': '✅',
    'closed': '✅',
}

# ==================== 存储配置 ====================

# 本地状态文件（用于记录任务完成状态，避免重复通知）
STATE_FILE = ".task_state.json"

# ==================== 工具函数 ====================

def get_display_name(account: str, use_alias: bool = True) -> str:
    """
    获取用户的显示名称
    
    Args:
        account: 禅道账号
        use_alias: 是否优先使用 ZENTAO_USER_DISPLAY_NAME 中的显示名
    
    Returns:
        显示名称
    """
    if use_alias and account in ZENTAO_USER_DISPLAY_NAME:
        return ZENTAO_USER_DISPLAY_NAME[account]
    return account


def get_feishu_user_id(account: str) -> str:
    """
    获取飞书用户 ID
    
    Args:
        account: 禅道账号
    
    Returns:
        飞书 open_id，如果没有映射则返回空字符串
    """
    return ZENTAO_FEISHU_USER_MAP.get(account, '')


def normalize_username(name: str) -> str:
    """
    标准化用户名（将各种变体转换为标准账号）
    
    Args:
        name: 可能的用户名变体
    
    Returns:
        标准的禅道账号
    """
    return ZENTAO_NAME_VARIANTS.get(name, name)


def should_exclude_user(account: str) -> bool:
    """
    判断用户是否应该被排除在统计之外
    
    Args:
        account: 禅道账号
    
    Returns:
        True 表示应该排除
    """
    return account in EXCLUDE_USERS


def is_tester(account: str) -> bool:
    """
    判断用户是否是测试人员
    
    Args:
        account: 禅道账号
    
    Returns:
        True 表示是测试人员
    """
    return account in TESTER_ACCOUNTS


# ==================== 配置验证 ====================

def validate_config():
    """验证配置的完整性"""
    errors = []
    
    # 检查必填配置
    if not ZENTAO_CONFIG.get('base_url'):
        errors.append("缺少禅道 base_url 配置")
    
    if not ZENTAO_CONFIG.get('username') or not ZENTAO_CONFIG.get('password'):
        errors.append("缺少禅道登录凭证")
    
    if not FEISHU_CONFIG.get('webhook') and not _config.has_section('project_webhook_map'):
        errors.append("缺少飞书 webhook 配置")

    if not PROJECT_PRODUCT_TARGETS:
        errors.append("缺少项目/产品与 webhook 的通知目标配置")

    for target in PROJECT_PRODUCT_TARGETS:
        if not target.get('webhook'):
            errors.append(
                f"通知目标缺少 webhook: project_id={target.get('project_id')}, "
                f"product_id={target.get('product_id')}"
            )
    
    # 检查用户映射一致性
    display_names = set(ZENTAO_USER_DISPLAY_NAME.keys())
    feishu_users = set(ZENTAO_FEISHU_USER_MAP.keys())
    
    if display_names != feishu_users:
        missing_in_display = feishu_users - display_names
        missing_in_feishu = display_names - feishu_users
        
        if missing_in_display:
            errors.append(f"以下用户在 ZENTAO_USER_DISPLAY_NAME 中缺失: {missing_in_display}")
        if missing_in_feishu:
            errors.append(f"以下用户在 ZENTAO_FEISHU_USER_MAP 中缺失: {missing_in_feishu}")
    
    return errors


if __name__ == '__main__':
    """配置测试"""
    print("=" * 60)
    print("禅道配置验证")
    print("=" * 60)
    
    errors = validate_config()
    if errors:
        print("❌ 配置验证失败:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✅ 配置验证通过")
    
    print("\n" + "=" * 60)
    print("配置信息汇总")
    print("=" * 60)
    
    print(f"\n📍 禅道配置:")
    print(f"  - API 地址: {ZENTAO_CONFIG['base_url']}")
    print(f"  - Web 地址: {ZENTAO_CONFIG['web_url']}")
    print(f"  - 用户名: {ZENTAO_CONFIG['username']}")
    print(f"  - 项目 ID: {PROJECT_CONFIG['project_id']}")
    print(f"  - 产品 ID: {PROJECT_CONFIG['product_id']}")
    
    print(f"\n📱 飞书配置:")
    if FEISHU_CONFIG['webhook']:
        print(f"  - Webhook: {FEISHU_CONFIG['webhook'][:50]}...")
    else:
        print("  - Webhook: 未设置（使用 project_webhook_map 中各目标 webhook）")
    print(f"  - 通知目标数: {len(PROJECT_PRODUCT_TARGETS)}")
    for idx, target in enumerate(PROJECT_PRODUCT_TARGETS, start=1):
        webhook_preview = str(target['webhook'])[:50]
        print(
            f"    {idx}. project_id={target['project_id']}, "
            f"product_id={target['product_id']}, webhook={webhook_preview}..."
        )
    
    print(f"\n👥 用户映射:")
    print(f"  - 总用户数: {len(ZENTAO_USER_DISPLAY_NAME)}")
    print(f"  - 测试人员: {', '.join([get_display_name(u) for u in TESTER_ACCOUNTS])}")
    print(f"  - 排除用户: {', '.join([get_display_name(u) for u in EXCLUDE_USERS])}")
    
    print(f"\n📋 所有用户信息:")
    for account in ZENTAO_USER_DISPLAY_NAME.keys():
        user_info = USERS[account]
        print(f"  - {account}:")
        print(f"    显示名: {get_display_name(account)}")
        print(f"    飞书ID: {get_feishu_user_id(account)[:20]}...")
        print(f"    名称变体: {', '.join(user_info['name_variants'])}")
        print(f"    是测试: {'是' if is_tester(account) else '否'}")
        print(f"    排除统计: {'是' if should_exclude_user(account) else '否'}")
