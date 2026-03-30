#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
禅道脚本统一入口
提供命令行方式调用各个禅道统计脚本
"""

import argparse
import sys


def show_help():
    """显示帮助信息"""
    help_text = """
📋 禅道脚本统一入口 - 使用说明

用法: python zentao_main.py <任务编号> [--period <周期>]

可用任务:
  1    每日待处理问题统计
  2    本周Bug统计
  3    本周任务统计
  4    本月Bug统计
  5    本月任务统计
  6    任务跟进监控
  7    周期统计报告 (支持季度/半年/年度)

周期报告参数 (仅任务7可用):
  --period quarter    季度报告(最近3个月)
  --period half       半年报告(最近6个月) [默认]
  --period year       年度报告(最近12个月)

示例:
  python zentao_main.py 1                    # 运行每日待处理问题统计
  python zentao_main.py 2                    # 运行本周Bug统计
  python zentao_main.py 7                    # 运行半年统计报告(默认)
  python zentao_main.py 7 --period quarter   # 运行季度统计报告
  python zentao_main.py 7 --period year      # 运行年度统计报告
  python zentao_main.py help                 # 显示此帮助信息
    """
    print(help_text)


def run_task(task_id: str, period: str = None):
    """
    运行指定的任务
    
    Args:
        task_id: 任务编号
        period: 周期参数（仅任务7使用）
    """
    print("=" * 60)
    
    if task_id == "1":
        print("🚀 正在运行: 每日待处理问题统计")
        print("=" * 60)
        import zentao_daily_pending
        result = zentao_daily_pending.main()
        
    elif task_id == "2":
        print("🚀 正在运行: 本周Bug统计")
        print("=" * 60)
        import zentao_weekly_bug
        result = zentao_weekly_bug.main()
        
    elif task_id == "3":
        print("🚀 正在运行: 本周任务统计")
        print("=" * 60)
        import zentao_weekly_task
        result = zentao_weekly_task.main()
        
    elif task_id == "4":
        print("🚀 正在运行: 本月Bug统计")
        print("=" * 60)
        import zentao_monthly_bug
        result = zentao_monthly_bug.main()
        
    elif task_id == "5":
        print("🚀 正在运行: 本月任务统计")
        print("=" * 60)
        import zentao_monthly_task
        result = zentao_monthly_task.main()
        
    elif task_id == "6":
        print("🚀 正在运行: 任务跟进监控")
        print("=" * 60)
        import zentao_task_monitor
        result = zentao_task_monitor.main()
        
    elif task_id == "7":
        print(f"🚀 正在运行: 周期统计报告 (period={period or 'half'})")
        print("=" * 60)
        import zentao_period_report
        result = zentao_period_report.main(period or 'half')
        
    else:
        print(f"❌ 未知任务: {task_id}")
        return 1
    
    print("=" * 60)
    if result == 0:
        print("✅ 任务执行完成")
    else:
        print(f"❌ 任务执行失败，退出码: {result}")
    print("=" * 60)
    
    return result


def main():
    """主入口函数"""
    # 如果没有传参数，显示help
    if len(sys.argv) == 1:
        show_help()
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        description="禅道脚本统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
可用任务:
  1 - 每日待处理问题统计
  2 - 本周Bug统计
  3 - 本周任务统计
  4 - 本月Bug统计
  5 - 本月任务统计
  6 - 任务跟进监控
  7 - 周期统计报告 (支持 --period quarter/half/year)
  help - 显示帮助信息

示例用法:
  %(prog)s 1                    # 每日待处理问题统计
  %(prog)s 2                    # 本周Bug统计
  %(prog)s 7 --period half      # 半年统计报告
  %(prog)s help                 # 显示帮助信息
        """
    )
    
    parser.add_argument(
        "task",
        choices=["1", "2", "3", "4", "5", "6", "7", "help"],
        help="要执行的任务编号 (输入 help 查看详细说明)"
    )
    
    parser.add_argument(
        "--period",
        choices=["quarter", "half", "year"],
        help="周期报告的统计周期 (仅任务7可用)"
    )
    
    args = parser.parse_args()
    
    # 如果是 help 命令，显示帮助并退出
    if args.task == "help":
        show_help()
        sys.exit(0)
    
    # 运行任务
    result = run_task(args.task, args.period)
    sys.exit(result)


if __name__ == "__main__":
    main()
