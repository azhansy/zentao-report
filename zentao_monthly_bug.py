from collections import defaultdict

# 导入统一配置
from zentao_config import (
    ZENTAO_CONFIG,
    API_CONFIG,
    PROJECT_PRODUCT_TARGETS,
    normalize_username,
    get_display_name,
    should_exclude_user,
)
from zentao_utils import (
    login_zentao,
    get_zentao_headers,
    get_current_month,
    send_feishu_message,
    create_feishu_post_message,
    format_date,
    request_json,
)

# ========== 配置 ==========
BASE_URL = ZENTAO_CONFIG['base_url']


def main():
    """本月Bug统计主函数"""
    PAGE = API_CONFIG['page']
    LIMIT = API_CONFIG['limit']
    
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
    
    # ========== 本月时间区间 ==========
    first_day_of_month, last_day_of_month = get_current_month()
    
    print("本月开始：", format_date(first_day_of_month))
    print("本月结束：", format_date(last_day_of_month))
    
    all_success = True

    for target in PROJECT_PRODUCT_TARGETS:
        product_id = target['product_id']
        project_id = target['project_id']
        webhook = target['webhook']
        product_name = get_product_name(product_id)

        print(f"\n📌 处理目标: project_id={project_id}, product_id={product_id}")

        opened_count = defaultdict(int)
        resolved_count = defaultdict(int)
        closed_count = defaultdict(int)
        pending_count = defaultdict(int)

        page = PAGE
        while True:
            url = f"{BASE_URL}/products/{product_id}/bugs?page={page}&limit={LIMIT}&status=all"
            data = request_json("GET", url, headers=headers)
            if not data:
                print("❌ 获取 Bug 列表失败")
                all_success = False
                break
            bugs = data.get("bugs", [])
            if not bugs:
                break

            has_data_in_range = False

            for bug in bugs:
                opened_in_range = False
                resolved_in_range = False
                closed_in_range = False

                from zentao_utils import parse_zentao_datetime

                opened_date = bug.get("openedDate")
                if opened_date:
                    opened_time = parse_zentao_datetime(opened_date)
                    if opened_time and first_day_of_month <= opened_time <= last_day_of_month:
                        opener = bug.get("openedBy", {}).get("realname", "未知")
                        opener = get_display_name(normalize_username(opener))
                        opened_count[opener] += 1
                        opened_in_range = True

                resolved_date = bug.get("resolvedDate")
                resolved_by = (bug.get("resolvedBy") or {}).get("realname")
                if resolved_date and resolved_by:
                    resolved_time = parse_zentao_datetime(resolved_date)
                    if resolved_time and first_day_of_month <= resolved_time <= last_day_of_month:
                        resolved_by = get_display_name(normalize_username(resolved_by))
                        resolved_count[resolved_by] += 1
                        resolved_in_range = True

                closed_date = bug.get("closedDate")
                closed_by = (bug.get("closedBy") or {}).get("realname")
                if closed_date and closed_by:
                    closed_time = parse_zentao_datetime(closed_date)
                    if closed_time and first_day_of_month <= closed_time <= last_day_of_month:
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

            page += 1

        all_users = set(opened_count) | set(resolved_count) | set(closed_count) | set(pending_count)
        stat_list = []

        for user in all_users:
            if should_exclude_user(user):
                continue

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

        title = (
            f"📊 本月 Bug 统计（{format_date(first_day_of_month)} ~ {format_date(last_day_of_month)}）"
            f" [{product_name}]"
        )
        payload = create_feishu_post_message(title, lines)

        success = send_feishu_message(payload, webhook=webhook)

        if success:
            print("✅ 飞书发送成功")
        else:
            print("❌ 发送失败")
            all_success = False

    return 0 if all_success else 1


if __name__ == "__main__":
    exit(main())
