#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
禅道每日待处理问题统计
统计当前待处理的Bug：未解决Bug(active)和待回归Bug(resolved)
"""

import requests
from collections import defaultdict

# 导入统一配置
from zentao_config import (
    ZENTAO_CONFIG,
    API_CONFIG,
    DISPLAY_CONFIG,
    PROJECT_PRODUCT_TARGETS,
    USERS,
    normalize_username,
    get_display_name,
)
from zentao_utils import (
    login_zentao,
    get_zentao_headers,
    send_feishu_message,
    pad_text,
)


def main():
    """主函数"""
    # ========== 配置 ==========
    BASE_URL = ZENTAO_CONFIG['base_url']
    ZENTAO_WEB_URL = ZENTAO_CONFIG['web_url']
    PAGE, LIMIT = API_CONFIG['page'], 100
    FIXED_USER_WIDTH = DISPLAY_CONFIG['fixed_user_width']

    # 测试人员集合（从配置中提取）
    TESTERS = {user_data['display_name'] for user, user_data in USERS.items() if user_data.get('is_tester', False)}

    # 设计师和产品经理集合（待确认类型）
    CONFIRM_USERS = {'阿梦', '茶哥', '城勤'}  # 设计师和产品经理

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
            resp = requests.get(url, headers=headers, verify=False, timeout=15)
            if resp.status_code != 200:
                return f"产品{product_id}"

            data = resp.json()
            if isinstance(data, dict):
                if data.get("name"):
                    return str(data["name"])

                product_obj = data.get("product")
                if isinstance(product_obj, dict) and product_obj.get("name"):
                    return str(product_obj["name"])

            return f"产品{product_id}"
        except Exception:
            return f"产品{product_id}"

    all_success = True

    for target in PROJECT_PRODUCT_TARGETS:
        product_id = target['product_id']
        project_id = target['project_id']
        webhook = target['webhook']
        product_name = get_product_name(product_id)

        print(f"\n📌 处理目标: project_id={project_id}, product_id={product_id}")

        bug_url = f"{ZENTAO_WEB_URL}/bug-browse-{product_id}.html"

        # 统计未解决Bug分布
        active_bugs_count = defaultdict(int)
        pending_verify_count = defaultdict(int)
        pending_confirm_count = defaultdict(int)

        page = PAGE
        while True:
            url = f'{BASE_URL}/products/{product_id}/bugs?page={page}&limit={LIMIT}'
            resp = requests.get(url, headers=headers, verify=False)
            data = resp.json()
            bugs = data.get('bugs', [])
            if not bugs:
                break

            for bug in bugs:
                status = bug.get("status")
                assignee_raw = (bug.get("assignedTo") or {}).get("realname", "未指派")
                assignee = get_display_name(normalize_username(assignee_raw))

                if assignee in TESTERS and status == "resolved":
                    pending_verify_count[assignee] += 1
                    continue

                if assignee in CONFIRM_USERS and status == "active":
                    pending_confirm_count[assignee] += 1
                    continue

                if status == "active":
                    active_bugs_count[assignee] += 1

            if page * LIMIT >= data.get('total', 0):
                break
            page += 1

        # ---------- ✨ 格式化输出 ----------
        def format_lines(data_map, label):
            """格式化统计行"""
            lines = []
            for user, count in sorted(data_map.items(), key=lambda x: x[1], reverse=True):
                padded_user = pad_text(user, FIXED_USER_WIDTH)
                lines.append(f"- {padded_user} ： {str(count).rjust(2)} {label}")
            return lines

        lines_active = format_lines(active_bugs_count, "个 Bug")
        lines_pending = format_lines(pending_verify_count, "个待回归")
        lines_confirm = format_lines(pending_confirm_count, "个待确认")

        # ---------- ✨ 飞书内容 ----------
        feishu_content = []

        # 未解决 Bug
        feishu_content.append([{"tag": "text", "text": "🐞 未解决 Bug（active）"}])
        if lines_active:
            for line in lines_active:
                feishu_content.append([{"tag": "text", "text": line}])
        else:
            feishu_content.append([{"tag": "text", "text": "暂无未解决 Bug"}])
        feishu_content.append([])

        # 待回归 Bug
        feishu_content.append([{"tag": "text", "text": "🧪 待回归（开发人员已解决但未关闭）"}])
        if lines_pending:
            for line in lines_pending:
                feishu_content.append([{"tag": "text", "text": line}])
        else:
            feishu_content.append([{"tag": "text", "text": "暂无待回归"}])
        feishu_content.append([])

        # 待确认 Bug
        feishu_content.append([{"tag": "text", "text": "📋 待确认（设计师/产品经理需确认）"}])
        if lines_confirm:
            for line in lines_confirm:
                feishu_content.append([{"tag": "text", "text": line}])
        else:
            feishu_content.append([{"tag": "text", "text": "暂无待确认"}])
        feishu_content.append([])

        # 查看详情
        feishu_content.append([
            {"tag": "a", "text": "👉 查看详情", "href": bug_url}
        ])

        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"📌 今日待处理Bug，请尽快完成！[{product_name}]",
                        "content": feishu_content
                    }
                }
            }
        }

        success = send_feishu_message(payload, webhook=webhook)
        if success:
            print("✅ 飞书发送成功")
        else:
            print("❌ 发送失败")
            all_success = False

    return 0 if all_success else 1


if __name__ == "__main__":
    exit(main())
