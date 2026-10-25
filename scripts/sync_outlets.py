"""
Script đồng bộ danh mục cửa hàng từ CSDL MS-SQL sang master_outlets.json
- Nguồn dữ liệu: Bảng G_Outlet JOIN G_Brand (IsActive = 1 AND IsUsed = 1)
- Đích: master_outlets.json (UTF-8) + ghi vết lịch sử sync_history.json
- Cơ chế bảo vệ: Chặn không cho chạy cron tự động trên môi trường DEV
"""
import os
import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("FREETDSCONF", str(BASE_DIR / "freetds.conf"))

import db


def main():
    parser = argparse.ArgumentParser(description="GigaMall Outlet & Brand Synchronization Script")
    parser.add_argument("--force", action="store_true", help="Bắt buộc chạy kể cả trên môi trường DEV")
    parser.add_argument("--actor", default="cron_system", help="Định danh tác tử thực hiện (mặc định: cron_system)")
    parser.add_argument("--source", default="CRON_JOB", help="Nguồn kích hoạt (mặc định: CRON_JOB)")
    args = parser.parse_args()

    cfg = db.load_db_config()
    env_name = cfg.get("_active_env", "dev").lower()

    # Chốt chặn an toàn: Môi trường DEV không chạy cron tự động
    if env_name == "dev" and not args.force:
        print("=" * 70)
        print("⚠️  CHỐT CHẶN AN TOÀN: MÔI TRƯỜNG DEV KHÔNG ĐƯỢC CHẠY CRON!")
        print("👉 Trên máy Dev (Mac), vui lòng sử dụng API hoặc chạy:")
        print("   python sync_from_api.py")
        print("👉 Nếu bạn vẫn muốn ép buộc đồng bộ trực tiếp từ DB Dev, hãy thêm cờ: --force")
        print("=" * 70)
        sys.exit(0)

    print(f"[*] Đang kết nối MS-SQL Server ({cfg.get('server')}:{cfg.get('port')}, DB: {cfg.get('database')}, Env: {env_name.upper()})...")
    try:
        count = db.sync_master_outlets_file(source=args.source, actor=args.actor)
        print(f"[+] ĐỒNG BỘ THÀNH CÔNG: Đã xuất {count} cửa hàng chuẩn vào master_outlets.json!")
    except Exception as e:
        print(f"[!] LỖI ĐỒNG BỘ: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
