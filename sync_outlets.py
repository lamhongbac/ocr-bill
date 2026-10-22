"""
Script đồng bộ danh mục cửa hàng từ CSDL MS-SQL (CLMHQ4GIGA) sang master_outlets.json
- Nguồn dữ liệu: Bảng G_Outlet JOIN G_Brand (IsActive = 1 AND IsUsed = 1)
- Đích: master_outlets.json (UTF-8)
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("FREETDSCONF", str(BASE_DIR / "freetds.conf"))

import db

def main():
    print("[*] Đang kết nối MS-SQL Server CLMHQ4GIGA...")
    try:
        count = db.sync_master_outlets_file()
        print(f"[+] ĐỒNG BỘ THÀNH CÔNG: Đã xuất {count} cửa hàng chuẩn vào master_outlets.json!")
    except Exception as e:
        print(f"[!] LỖI ĐỒNG BỘ: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
