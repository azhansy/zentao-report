from collections import defaultdict

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
    get_current_week,
    send_feishu_message,
    format_date,
    parse_zentao_datetime,
    request_json,
)

# ========== 配置 ==========
BASE_URL = ZENTAO_CONFIG['base_url']


def main():
    """本周Bug统计主函数"""
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
        data = request_json("GET", url, headers=headers)
        if not isinstance(data, dict):
            return f"产品{product_id}"

        if data.get("name"):
            return str(data["name"])

        product_obj = data.get("product")
        if isinstance(product_obj, dict) and product_obj.get("name"):
            return str(product_obj["name"])

        return f"产品{product_id}"
    
    # ========== 本周时间区间 ==========
    current_monday, current_sunday = get_current_week()
    
    all_success = True

    for target in PROJECT_PRODUCT_TARGETS:
        product_id = target['product_id']
        project_id = target['project_id']
        webhook = target['webhook']
        product_name = get_product_name(product_id)

        print(f"\n📌 处理目标: project_id={project_id}, product_id={product_id}")

        # ========== 统计初始化 ==========
        opened_count = defaultdict(int)
        resolved_count = defaultdict(int)
        closed_count = defaultdict(int)
        pending_count = defaultdict(int)

        seen_ids = set()
        page = PAGE

        while True:
            url = f"{BASE_URL}/products/{product_id}/bugs?page={page}&limit={LIMIT}&status=all"
            print(f"📥 拉取 Bug 列表: page={page}, limit={LIMIT}")
            data = request_json("GET", url, headers=headers)
            if not data:
                print("❌ 获取 Bug 列表失败")
                all_success = False
                break
            bugs = data.get("bugs", [])
            print(f"✅ 获取到 {len(bugs)} 条")
            if not bugs:
                break

            current_ids = {bug.get("id") for bug in bugs if bug.get("id") is not None}
            if not current_ids or current_ids.issubset(seen_ids):
                print("⚠️ 分页数据未变化，停止以避免死循环")
                break
            seen_ids.update(current_ids)

            has_data_in_range = False

            for bug in bugs:
                opened_in_range = False
                resolved_in_range = False
                closed_in_range = False

                opened_date = bug.get("openedDate")
                if opened_date:
                    opened_time = parse_zentao_datetime(opened_date)
                    if opened_time and current_monday <= opened_time <= current_sunday:
                        opener = bug.get("openedBy", {}).get("realname", "未知")
                        opener = get_display_name(normalize_username(opener))
                        opened_count[opener] += 1
                        opened_in_range = True

                resolved_date = bug.get("resolvedDate")
                resolved_by = (bug.get("resolvedBy") or {}).get("realname")
                if resolved_date and resolved_by:
                    resolved_time = parse_zentao_datetime(resolved_date)
                    if resolved_time and current_monday <= resolved_time <= current_sunday:
                        resolved_by = get_display_name(normalize_username(resolved_by))
                        resolved_count[resolved_by] += 1
                        resolved_in_range = True

                closed_date = bug.get("closedDate")
                closed_by = (bug.get("closedBy") or {}).get("realname")
                if closed_date and closed_by:
                    closed_time = parse_zentao_datetime(closed_date)
                    if closed_time and current_monday <= closed_time <= current_sunday:
                        closed_by = get_display_name(normalize_username(closed_by))
                        closed_count[closed_by] += 1
                        closed_in_range = True

                assigned_to = (bug.get("assignedTo") or {}).get("realname")
                if assigned_to and not bug.get("resolvedDate"):
                    assigned_to = get_display_name(normalize_username(assigned_to))
                    pending_count[assigned_to] += 1

                if opened_in_range or resolved_in_range or closed_in_range:
                    has_data_in_range = True

            if not has_data_in_range:
                break

            total = data.get("total")
            if total and page * LIMIT >= total:
                break

            page += 1

        all_users = set(opened_count) | set(resolved_count) | set(closed_count) | set(pending_count)
        stat_list = []

        for user in all_users:
            stat_list.append({
                "user": user,
                "opened": opened_count.get(user, 0),
                "closed": closed_count.get(user, 0),
                "resolved": resolved_count.get(user, 0),
                "pending": pending_count.get(user, 0),
            })

        stat_list.sort(key=lambda x: (-x["opened"], -x["resolved"]))

        lines = []

        for idx, row in enumerate(stat_list, start=1):
            line = {
                "tag": "text",
                "text": f"{idx}. {row['user']}   🔍 发现🐞/回归✅：{row['opened']}/{row['closed']}   ✅ 解决：{row['resolved']}  🕐 待解决：{row['pending']}"
            }
            lines.append([line])

        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": (
                            f"📊 本周 Bug 统计（{format_date(current_monday)} ~ {format_date(current_sunday)}）"
                            f" [{product_name}]"
                        ),
                        "content": lines,
                    }
                }
            }
        }

        print("📤 正在发送飞书消息...")
        success = send_feishu_message(payload, webhook=webhook)
        if success:
            print("✅ 飞书发送成功")
        else:
            print("❌ 发送失败")
            all_success = False

    return 0 if all_success else 1


if __name__ == "__main__":
    exit(main())
