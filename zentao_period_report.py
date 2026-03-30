#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
禅道周期统计报告
用于生成季度/半年/全年的汇总统计数据，支持集团汇报使用
"""

import requests
import argparse
from collections import defaultdict
from datetime import datetime, timedelta

# 导入统一配置
from zentao_config import (
    ZENTAO_CONFIG,
    API_CONFIG,
    PROJECT_PRODUCT_TARGETS,
    normalize_username,
    get_display_name,
)
from zentao_utils import (
    login_zentao,
    get_zentao_headers,
    send_feishu_message,
    format_date,
    parse_zentao_datetime,
)

# ========== 配置 ==========
BASE_URL = ZENTAO_CONFIG['base_url']


# ========== 时间段计算 ==========
def get_period_range(period_type: str):
    """
    根据周期类型计算开始和结束时间
    
    Args:
        period_type: 'quarter'(季度), 'half'(半年), 'year'(全年)
    
    Returns:
        (start_date, end_date) 元组
    """
    today = datetime.now()
    
    if period_type == 'quarter':  # 最近3个月
        start_date = today - timedelta(days=90)
        title = "季度"
    elif period_type == 'half':  # 最近6个月
        start_date = today - timedelta(days=180)
        title = "半年"
    elif period_type == 'year':  # 最近12个月
        start_date = today - timedelta(days=365)
        title = "年度"
    else:
        raise ValueError(f"不支持的周期类型: {period_type}")
    
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return start_date, end_date, title


# ========== 主函数 ==========
def main(period_type='half'):
    """生成周期统计报告"""
    PAGE = API_CONFIG['page']
    LIMIT = 100
    
    # ========== 获取 Token ==========
    token = login_zentao(use_curl=True)
    if not token:
        print("❌ 登录失败，退出程序")
        return 1
    headers = get_zentao_headers(token)

    def get_product_name(product_id: int) -> str:
        """获取产品名称，失败时回退为产品ID。"""
        url = f"{BASE_URL}/products/{product_id}"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return f"产品{product_id}"

            data = resp.json()
            if isinstance(data, dict):
                if data.get("name"):
                    return str(data["name"])
                product_obj = data.get("product")
                if isinstance(product_obj, dict) and product_obj.get("name"):
                    return str(product_obj["name"])
        except Exception:
            pass
        return f"产品{product_id}"
    
    # 获取时间范围
    start_date, end_date, period_title = get_period_range(period_type)
    print(f"📊 正在统计 {period_title} 数据...")
    print(f"   时间范围: {format_date(start_date)} ~ {format_date(end_date)}")
    
    all_success = True

    for target in PROJECT_PRODUCT_TARGETS:
        project_id = target['project_id']
        product_id = target['product_id']
        webhook = target['webhook']
        product_name = get_product_name(product_id)

        print(f"\n📌 处理目标: project_id={project_id}, product_id={product_id}")

        print("\n📋 获取执行列表...")
        executions = []
        page = 1
        while True:
            url = f"{BASE_URL}/projects/{project_id}/executions?page={page}&limit={LIMIT}"
            resp = requests.get(url, headers=headers)
            data = resp.json()
            ex_list = data.get("executions", [])
            if not ex_list:
                break
            executions.extend(ex_list)
            if page * LIMIT >= data.get("total", 0):
                break
            page += 1

        print(f"   ✅ 获取到 {len(executions)} 个执行")

        total_executions = 0
        total_tasks = 0
        total_bugs = 0
        user_executions = defaultdict(set)
        user_tasks = defaultdict(int)

        print("\n📝 统计任务数据...")
        for exec_item in executions:
            exec_id = exec_item.get("id")
            total_executions += 1

            task_page = 1
            while True:
                url = f"{BASE_URL}/executions/{exec_id}/tasks?status=all&page={task_page}&limit={LIMIT}"
                resp = requests.get(url, headers=headers)
                task_data = resp.json()
                tasks = task_data.get("tasks", [])
                if not tasks:
                    break

                for task in tasks:
                    task_id = task.get("id")
                    task_detail = requests.get(f"{BASE_URL}/tasks/{task_id}", headers=headers).json()

                    if "error" in task_detail:
                        continue

                    created_date = task_detail.get("openedDate")
                    if created_date:
                        created_time = parse_zentao_datetime(created_date)
                        if created_time and start_date <= created_time <= end_date:
                            total_tasks += 1

                            assigned = task_detail.get("assignedTo")
                            if assigned and isinstance(assigned, dict):
                                account = assigned.get("account", "")
                                if account:
                                    account = normalize_username(account)
                                    display_name = get_display_name(account)
                                    user_executions[display_name].add(exec_id)
                                    user_tasks[display_name] += 1

                            team = task_detail.get("team", [])
                            if isinstance(team, list):
                                for member in team:
                                    if isinstance(member, dict):
                                        account = member.get("account", "")
                                        if account:
                                            account = normalize_username(account)
                                            display_name = get_display_name(account)
                                            user_executions[display_name].add(exec_id)
                                            user_tasks[display_name] += 1

                if task_page * LIMIT >= task_data.get("total", 0):
                    break
                task_page += 1

        print(f"   ✅ 统计到 {total_tasks} 个任务")

        print("\n🐞 统计Bug数据...")
        page = 1
        while True:
            url = f"{BASE_URL}/products/{product_id}/bugs?page={page}&limit={LIMIT}&status=all"
            resp = requests.get(url, headers=headers)
            data = resp.json()
            bugs = data.get("bugs", [])
            if not bugs:
                break

            for bug in bugs:
                opened_date = bug.get("openedDate")
                if opened_date:
                    opened_time = parse_zentao_datetime(opened_date)
                    if opened_time and start_date <= opened_time <= end_date:
                        total_bugs += 1

            if page * LIMIT >= data.get("total", 0):
                break
            page += 1

        print(f"   ✅ 统计到 {total_bugs} 个Bug")

        print("\n📤 生成报告...")
        lines = []
        lines.append([{"tag": "text", "text": f"📊 {period_title}数据汇总"}])
        lines.append([{"tag": "text", "text": f"⏰ 统计周期：{format_date(start_date)} ~ {format_date(end_date)}"}])
        lines.append([])
        lines.append([{"tag": "text", "text": "📈 总体数据"}])
        lines.append([{"tag": "text", "text": f"• 执行总数：{total_executions} 个"}])
        lines.append([{"tag": "text", "text": f"• 任务总数：{total_tasks} 个"}])
        lines.append([{"tag": "text", "text": f"• Bug总数：{total_bugs} 个"}])
        lines.append([])

        if user_executions:
            lines.append([{"tag": "text", "text": "👥 成员参与统计"}])
            sorted_users = sorted(
                user_executions.items(),
                key=lambda x: (len(x[1]), user_tasks.get(x[0], 0)),
                reverse=True,
            )
            for idx, (user, exec_ids) in enumerate(sorted_users, start=1):
                task_count = user_tasks.get(user, 0)
                lines.append([{
                    "tag": "text",
                    "text": f"{idx}. {user}：参与 {len(exec_ids)} 个执行，完成 {task_count} 个任务"
                }])
            lines.append([])

        lines.append([{"tag": "text", "text": "💡 数据说明"}])
        lines.append([{"tag": "text", "text": "• 任务数据基于任务创建时间统计"}])
        lines.append([{"tag": "text", "text": "• Bug数据基于Bug创建时间统计"}])
        lines.append([{"tag": "text", "text": "• 人员参与度按执行数量和任务数量排序"}])

        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"📊 {period_title}工作统计报告 [{product_name}]",
                        "content": lines
                    }
                }
            }
        }

        success = send_feishu_message(payload, webhook=webhook)
        if success:
            print("\n✅ 报告已发送到飞书")
        else:
            print("\n❌ 发送失败")
            all_success = False

    return 0 if all_success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="禅道周期统计报告")
    parser.add_argument(
        "--period",
        choices=["quarter", "half", "year"],
        default="half",
        help="统计周期：quarter(季度), half(半年), year(全年)，默认为半年"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("禅道周期统计报告")
    print("=" * 60)
    
    exit_code = main(args.period)
    
    print("\n" + "=" * 60)
    print("统计完成")
    print("=" * 60)
    
    exit(exit_code)
