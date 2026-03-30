#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
import os
import subprocess

# 导入统一配置
from zentao_config import (
    ZENTAO_CONFIG,
    PROJECT_PRODUCT_TARGETS,
    ZENTAO_FEISHU_USER_MAP,
    ZENTAO_USER_DISPLAY_NAME,
    TESTER_ACCOUNTS,
    ZENTAO_NAME_VARIANTS,
    STATE_FILE,
)
from zentao_utils import (
    login_zentao,
    get_zentao_headers,
    get_task_web_url,
)

# =======================
# 获取未完成的任务，每个节点完成后，就通知未完成的用户
# =======================

# ========== 配置 ==========
BASE_URL = ZENTAO_CONFIG['base_url']
ZENTAO_WEB_URL = ZENTAO_CONFIG['web_url']
USERNAME = ZENTAO_CONFIG['username']
PASSWORD = ZENTAO_CONFIG['password']
DEFAULT_TARGET = PROJECT_PRODUCT_TARGETS[0]
PROJECT_ID = DEFAULT_TARGET['project_id']
PRODUCT_ID = DEFAULT_TARGET['product_id']
FEISHU_WEBHOOK = DEFAULT_TARGET['webhook']
PAGE, LIMIT = 1, 300


# =======================
# 工具函数
# =======================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def login_zentao_curl():
    """禅道登录获取 token - 使用 curl 绕过 WAF（保留用于特殊情况）"""
    # 现在优先使用 utils 中的 login_zentao(use_curl=True)
    return login_zentao(use_curl=True)


def fetch_project_executions(token):
    """获取项目的所有执行列表 - 使用 curl"""
    url = f"{BASE_URL}/projects/{PROJECT_ID}/executions?page={PAGE}&limit={LIMIT}"

    try:
        cmd = ['curl', '-s', '-X', 'GET', url, '-H', f'Token: {token}']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            print(f"❌ 获取项目执行列表失败: {result.stderr}")
            return []
        
        resp_json = json.loads(result.stdout)
        
        if isinstance(resp_json, dict) and 'executions' in resp_json:
            executions = resp_json['executions']
            print(f"✅ 获取到 {len(executions)} 个执行")
            return executions
        else:
            print(f"⚠️  未找到项目执行")
            return []
    except Exception as e:
        print(f"❌ 获取项目执行列表出错: {e}")
        return []


def fetch_execution_tasks(token, execution_id):
    """获取执行下的所有进行中的任务 - 使用 curl"""
    url = f"{BASE_URL}/executions/{execution_id}/tasks?status=doing&page={PAGE}&limit={LIMIT}"

    try:
        cmd = ['curl', '-s', '-X', 'GET', url, '-H', f'Token: {token}']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            print(f"❌ 获取执行任务失败 (执行ID: {execution_id}): {result.stderr}")
            return []
        
        resp_json = json.loads(result.stdout)
        
        if isinstance(resp_json, dict) and 'tasks' in resp_json:
            tasks = resp_json['tasks']
            return tasks
        elif isinstance(resp_json, list):
            return resp_json
        else:
            return []
    except Exception as e:
        print(f"❌ 获取执行任务出错 (执行ID: {execution_id}): {e}")
        return []


def fetch_task_detail(token, task_id):
    """查询任务详情（团队任务的成员状态）- 使用 curl"""
    url = f"{BASE_URL}/tasks/{task_id}"

    try:
        cmd = ['curl', '-s', '-X', 'GET', url, '-H', f'Token: {token}']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            print(f"❌ 获取任务详情失败 (任务ID: {task_id}): {result.stderr}")
            return {}
        
        return json.loads(result.stdout)
    except Exception as e:
        print(f"❌ 获取任务详情出错 (任务ID: {task_id}): {e}")
        return {}


def get_team_finish_order(detail):
    """
    从任务详情中获取团队成员完成顺序
    返回按完成时间倒序排序的成员账号列表（最新完成的排在前面）
    """
    team = detail.get("team", [])
    actions = detail.get("actions", [])
    
    # 构建成员完成时间映射
    finish_times = {}
    
    for action in actions:
        # 查找 finished 动作
        if action.get("action") == "finished":
            actor = action.get("actor")
            date = action.get("date")
            
            if actor and date:
                # 使用 ZENTAO_NAME_VARIANTS 映射获取账号
                actor_account = ZENTAO_NAME_VARIANTS.get(actor)
                
                # 如果是团队成员的完成动作
                if actor_account:
                    for member in team:
                        if member.get("account") == actor_account and member.get("status") == "done":
                            # 记录完成时间（保留最新的完成时间）
                            finish_times[actor_account] = date
                            break
    
    # 获取所有已完成的团队成员
    finished_members = [m["account"] for m in team if m["status"] == "done"]
    
    # 按完成时间倒序排序（最新完成的排在前面）
    sorted_finished = sorted(
        finished_members,
        key=lambda account: finish_times.get(account, "0000-00-00 00:00:00"),
        reverse=True  # 倒序
    )
    
    return sorted_finished


def send_feishu(content: str, user_accounts: list = None, task_id: str = None, task_name: str = None, finished_members: list = None):
    """
    飞书发送消息
    如果提供了 user_accounts 列表，则发送 @多个用户 的通知
    如果提供了 task_id 和 task_name，则使用富文本消息带上任务链接
    finished_members: 完成的成员列表（按时间倒序），第一个会加粗显示
    """
    # 如果有任务信息，使用富文本消息
    if task_id and task_name:
        task_url = get_task_web_url(task_id)
        
        # 构建富文本内容
        content_parts = []
        
        # 如果需要 @多个用户
        if user_accounts:
            for i, user_account in enumerate(user_accounts):
                if user_account in ZENTAO_FEISHU_USER_MAP:
                    feishu_uid = ZENTAO_FEISHU_USER_MAP[user_account]
                    if feishu_uid:
                        content_parts.append({
                            "tag": "at",
                            "user_id": feishu_uid
                        })
                        # 在每个@之后添加空格
                        if i < len(user_accounts) - 1:
                            content_parts.append({
                                "tag": "text",
                                "text": " "
                            })
            
            # 在所有@之后添加空格
            if content_parts:
                content_parts.append({
                    "tag": "text",
                    "text": " "
                })
        
        # 添加完成成员名称（第一个用🔥标记）
        if finished_members:
            for i, member_account in enumerate(finished_members):
                member_name = ZENTAO_USER_DISPLAY_NAME.get(member_account, member_account)
                
                if i == 0:
                    # 第一个成员（最新完成的）加🔥标记
                    content_parts.append({
                        "tag": "text",
                        "text": f"🔥{member_name}"
                    })
                else:
                    # 其他成员正常显示
                    content_parts.append({
                        "tag": "text",
                        "text": member_name
                    })
                
                # 添加顿号分隔（除了最后一个）
                if i < len(finished_members) - 1:
                    content_parts.append({
                        "tag": "text",
                        "text": "、"
                    })
            
            # 添加后续文本
            content_parts.append({
                "tag": "text",
                "text": " 刚刚完成了任务，" + ("现在可以开始测试了。" if "测试" in content else "请尽快跟进。")
            })
        else:
            # 如果没有提供finished_members，使用原来的content
            content_parts.append({
                "tag": "text",
                "text": content.replace(f"《{task_name}》", "")
            })
        
        # 添加任务链接
        content_parts.append({
            "tag": "a",
            "text": f"《{task_name}》",
            "href": task_url
        })
        
        data = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": "执行任务提醒",
                        "content": [
                            content_parts
                        ]
                    }
                }
            }
        }
    else:
        # 普通文本消息
        if user_accounts:
            at_text = ""
            for user_account in user_accounts:
                if user_account in ZENTAO_FEISHU_USER_MAP:
                    feishu_uid = ZENTAO_FEISHU_USER_MAP[user_account]
                    if feishu_uid:
                        at_text += f'<at user_id="{feishu_uid}"></at> '
            
            if at_text:
                data = {
                    "msg_type": "text",
                    "content": {
                        "text": f"{at_text}{content}"
                    }
                }
            else:
                data = {
                    "msg_type": "text",
                    "content": {"text": content}
                }
        else:
            data = {
                "msg_type": "text",
                "content": {"text": content}
            }
    
    try:
        response = requests.post(FEISHU_WEBHOOK, json=data)
        if response.status_code != 200:
            print(f"  ⚠️  飞书返回错误状态码: {response.status_code}, 响应: {response.text}")
    except Exception as e:
        print(f"  ⚠️  发送飞书消息失败: {e}")


# =======================
# 主流程
# =======================

def main():
    """团队任务监控主函数"""
    state = load_state()

    print("开始检查禅道团队任务…")

    # 使用 utils 中的登录函数（curl 方式）
    token = login_zentao_curl()
    if not token:
        print("禅道登录失败")
        return 1

    # 获取项目的所有执行
    executions = fetch_project_executions(token)
    
    if not executions:
        print("✅ 当前项目没有执行")
        return
    
    all_tasks = []
    # 遍历每个执行，获取其进行中的任务
    for execution in executions:
        exec_id = execution.get("id")
        exec_name = execution.get("name", "未命名")
        print(f"\n📦 检查执行: {exec_name} (ID: {exec_id})")
        
        tasks = fetch_execution_tasks(token, exec_id)
        if tasks:
            print(f"  ✅ 找到 {len(tasks)} 个进行中的任务")
            all_tasks.extend(tasks)
        else:
            print(f"  ℹ️  没有进行中的任务")
    
    if not all_tasks:
        print("\n✅ 当前没有进行中的团队任务")
        return

    print(f"\n📋 共找到 {len(all_tasks)} 个进行中的任务")

    for task in all_tasks:
        task_id = str(task["id"])
        name = task["name"]

        print(f"\n📋 检查任务: {name} (ID: {task_id})")

        detail = fetch_task_detail(token, task_id)

        # team 为团队成员
        team = detail.get("team", [])
        if not team:
            print(f"  ℹ️  不是团队任务，跳过")
            continue

        # 记录已完成成员（按完成时间排序）
        finished_members = get_team_finish_order(detail)
        unfinished_members = [m["account"] for m in team if m["status"] != "done"]

        print(f"  ✅ 已完成成员: {finished_members if finished_members else '无'}")
        print(f"  ⏳ 未完成成员: {unfinished_members if unfinished_members else '无'}")

        old_finished = state.get(task_id, [])

        # 找出 "新完成" 的成员（保持顺序）
        new_finished = [m for m in finished_members if m not in old_finished]

        if new_finished:
            # 有人新完成 → 判断是否需要通知
            print(f"  🔔 发现新完成成员: {new_finished}")
            
            # 分离测试人员和非测试人员
            testers_unfinished = [m for m in unfinished_members if m in TESTER_ACCOUNTS]
            non_testers_unfinished = [m for m in unfinished_members if m not in TESTER_ACCOUNTS]
            
            # 获取新完成成员的显示名称
            finished_names = [ZENTAO_USER_DISPLAY_NAME.get(m, m) for m in new_finished]
            finished_names_str = '、'.join(finished_names)
            
            # 1. 通知非测试人员（无论什么情况都通知）
            if non_testers_unfinished:
                msg = f"{finished_names_str} 刚刚完成了任务，请尽快跟进。"
                send_feishu(msg, non_testers_unfinished, task_id, name, new_finished)
                non_testers_names = [ZENTAO_USER_DISPLAY_NAME.get(m, m) for m in non_testers_unfinished]
                print(f"  📤 已通知: {', '.join(non_testers_names)}")
            
            # 2. 只有当非测试人员都完成了，才通知测试人员
            if not non_testers_unfinished and testers_unfinished:
                print(f"  ℹ️  所有非测试人员已完成，开始通知测试人员")
                msg = f"{finished_names_str} 刚刚完成了任务，现在可以开始测试了。"
                send_feishu(msg, testers_unfinished, task_id, name, new_finished)
                testers_names = [ZENTAO_USER_DISPLAY_NAME.get(m, m) for m in testers_unfinished]
                print(f"  📤 已通知测试人员: {', '.join(testers_names)}")
            elif testers_unfinished and non_testers_unfinished:
                print(f"  ⏸️  还有非测试人员未完成 {non_testers_unfinished}，暂不通知测试人员")

        # 更新本地状态
        state[task_id] = finished_members

    save_state(state)
    print("\n✅ 检查完成。")
    return 0


if __name__ == "__main__":
    exit(main())
