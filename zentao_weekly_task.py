import requests
from collections import defaultdict

from zentao_config import (
    ZENTAO_CONFIG,
    PROJECT_PRODUCT_TARGETS,
    normalize_username,
    get_display_name,
)
from zentao_utils import (
    login_zentao,
    get_zentao_headers,
    get_current_week,
    get_task_web_url,
    send_feishu_message,
    create_feishu_post_message,
    format_date,
    pad_text,
    parse_zentao_datetime,
)

BASE_URL = ZENTAO_CONFIG['base_url']


def main():
    """本周任务统计主函数"""
    limit = 100

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

    this_monday, this_sunday = get_current_week()
    all_success = True

    for target in PROJECT_PRODUCT_TARGETS:
        project_id = target['project_id']
        product_id = target['product_id']
        webhook = target['webhook']
        product_name = get_product_name(product_id)

        print(f"\n📌 处理目标: project_id={project_id}, product_id={product_id}")

        executions = []
        page = 1
        while True:
            url = f"{BASE_URL}/projects/{project_id}/executions?page={page}&limit={limit}"
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                print(f"❌ 请求失败: {resp.status_code} - {resp.text}")
                all_success = False
                break

            data = resp.json()
            ex_list = data.get("executions", [])
            if not ex_list:
                break
            executions.extend(ex_list)
            if page * limit >= data.get("total", 0):
                break
            page += 1

        finished_count = defaultdict(int)
        pending_tasks = []
        closed_tasks = []
        account_to_realname = {}

        for exec_item in executions:
            exec_id = exec_item.get("id")
            task_page = 1
            while True:
                url = f"{BASE_URL}/executions/{exec_id}/tasks?status=all&page={task_page}&limit={limit}"
                resp = requests.get(url, headers=headers)
                if resp.status_code != 200:
                    print(f"❌ 请求失败: {resp.status_code} - {resp.text}")
                    all_success = False
                    break

                task_data = resp.json()
                tasks = task_data.get("tasks", [])
                if not tasks:
                    break

                for task in tasks:
                    task_id = task.get("id")
                    task_status = task.get("status")

                    detail_resp = requests.get(f"{BASE_URL}/tasks/{task_id}", headers=headers)
                    if detail_resp.status_code != 200 or not detail_resp.text.strip():
                        continue

                    task_detail = detail_resp.json()
                    if "error" in task_detail:
                        continue

                    assigned = task_detail.get("assignedTo")
                    if assigned and isinstance(assigned, dict):
                        account = assigned.get("account", "")
                        realname = assigned.get("realname", "")
                        if account and realname and not realname.isdigit():
                            account_to_realname[account] = realname

                    team = task_detail.get("team", [])
                    if isinstance(team, list):
                        for member in team:
                            if isinstance(member, dict):
                                account = member.get("account", "")
                                realname = member.get("realname", "")
                                if account and realname and not realname.isdigit():
                                    account_to_realname[account] = realname

                    for act in task_detail.get("actions", []):
                        if act.get("action") == "finished":
                            dt = parse_zentao_datetime(act.get("date"))
                            if dt and this_monday <= dt <= this_sunday:
                                actor = act.get("actor", "")
                                if actor:
                                    actor = normalize_username(actor)
                                    finished_count[get_display_name(actor)] += 1

                    if task_status != "closed":
                        task_members = {}
                        task_overall_progress = task_detail.get("progress", 0)
                        team = task_detail.get("team", [])
                        if isinstance(team, list):
                            for member in team:
                                if isinstance(member, dict):
                                    account = member.get("account", "")
                                    if account:
                                        task_members[account] = {
                                            "progress": member.get("progress", 0),
                                            "status": member.get("status", ""),
                                        }

                        pending_tasks.append({
                            "id": task_id,
                            "name": task_detail.get("name", "未命名任务"),
                            "url": get_task_web_url(task_id),
                            "members": task_members,
                            "overall_progress": task_overall_progress,
                        })

                    closed_date = task_detail.get("closedDate")
                    if closed_date:
                        dt = parse_zentao_datetime(closed_date)
                        if dt and this_monday <= dt <= this_sunday:
                            closed_tasks.append({
                                "id": task_id,
                                "name": task_detail.get("name", "未命名任务"),
                                "url": get_task_web_url(task_id),
                            })

                if task_page * limit >= task_data.get("total", 0):
                    break
                task_page += 1

        def get_display_name_local(account):
            account = normalize_username(account)
            display = get_display_name(account)
            if display != account:
                return display
            return account_to_realname.get(account, account)

        lines = []
        if finished_count:
            lines.append([{"tag": "text", "text": "🔥 本周完成任务统计（多人完成动作累计）"}])
            for idx, (user, cnt) in enumerate(sorted(finished_count.items(), key=lambda x: -x[1]), start=1):
                lines.append([{"tag": "text", "text": f"{idx}. {pad_text(user)} ：完成 {cnt} 个任务"}])
            lines.append([])

        if pending_tasks:
            lines.append([{"tag": "text", "text": "📋 本周未关闭任务列表"}])
            for idx, task in enumerate(pending_tasks, start=1):
                lines.append([
                    {"tag": "text", "text": f"{idx}. "},
                    {"tag": "a", "text": task['name'], "href": task['url']},
                    {"tag": "text", "text": f" [整体进度: {task['overall_progress']}%]"},
                ])

                members_info = []
                sorted_members = sorted(
                    task['members'].items(),
                    key=lambda x: (-x[1]["progress"], 0 if x[1]["status"] == "done" else 1),
                )
                for account, info in sorted_members:
                    status_emoji = {
                        "done": "✅",
                        "doing": "🔄",
                        "wait": "⏸️",
                        "assigned": "📌",
                    }.get(info["status"], "❓")
                    members_info.append(f"{get_display_name_local(account)}{status_emoji}({info['progress']}%)")
                if members_info:
                    lines.append([{"tag": "text", "text": f"   👤 成员进度: {' | '.join(members_info)}"}])
            lines.append([])

        if closed_tasks:
            lines.append([{"tag": "text", "text": f"✅ 本周已关闭任务（共 {len(closed_tasks)} 个）"}])
            for idx, task in enumerate(closed_tasks, start=1):
                lines.append([
                    {"tag": "text", "text": f"{idx}. "},
                    {"tag": "a", "text": task['name'], "href": task['url']},
                ])
            lines.append([])

        title = (
            f"📌 本周任务统计（{format_date(this_monday)} ~ {format_date(this_sunday)}）"
            f" [{product_name}]"
        )
        payload = create_feishu_post_message(title, lines)
        success = send_feishu_message(payload, webhook=webhook)
        if not success:
            all_success = False

    return 0 if all_success else 1


if __name__ == "__main__":
    exit(main())
