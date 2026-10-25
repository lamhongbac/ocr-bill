#!/usr/bin/env python3
"""
Tiện ích dành cho môi trường DEV (máy Mac):
Đồng bộ danh mục Cửa hàng & Thương hiệu từ máy chủ Pilot/Prod về máy Mac thông qua API.
Không cần kết nối trực tiếp CSDL SQL Server từ máy Dev.

Cách dùng:
  python sync_from_api.py
  python sync_from_api.py --remote-sync  # Yêu cầu Server đồng bộ từ DB trước rồi mới tải về Mac
  python sync_from_api.py --host http://14.161.34.37:8080
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_OUTLETS_FILE = BASE_DIR / "master_outlets.json"
DEFAULT_HOST = "http://14.161.34.37:8080"


def sync_outlets_via_api(host: str, trigger_remote: bool = False, actor: str = "Dev_Mac"):
    host = host.rstrip("/")
    print("=" * 70)
    print("🚀 GIGAMALL OCR - ĐỒNG BỘ DANH MỤC CỬA HÀNG QUA API VỀ MÁY MAC")
    print(f"🎯 Máy chủ API: {host}")
    print(f"📁 Tệp đích cục bộ: {LOCAL_OUTLETS_FILE}")
    print("=" * 70)

    # 1. Kích hoạt Server đồng bộ từ CSDL (nếu được yêu cầu)
    if trigger_remote:
        print(f"\n[1/2] ⚡ Đang yêu cầu máy chủ đồng bộ từ CSDL MS-SQL (actor={actor})...")
        sync_url = f"{host}/api/v1/sync-outlets?actor={actor}&source=DEV_API"
        req = urllib.request.Request(sync_url, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"  ✓ Máy chủ phản hồi: {data.get('message', 'Thành công')}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"  ❌ Lỗi từ máy chủ (HTTP {e.code}): {err_body}")
            sys.exit(1)
        except Exception as e:
            print(f"  ❌ Không thể kết nối tới {sync_url}: {e}")
            sys.exit(1)
    else:
        print("\n[1/2] ℹ️ Bỏ qua bước yêu cầu server sync DB (dùng danh mục hiện hữu trên server). Thêm cờ --remote-sync nếu muốn ép server sync DB.")

    # 2. Tải danh mục về máy Mac
    print(f"\n[2/2] 📥 Đang tải danh mục cửa hàng từ {host}/api/outlets...")
    download_url = f"{host}/api/outlets"
    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": "GigaMall-Dev-Sync/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            outlets = json.loads(content.decode("utf-8-sig"))

        if not isinstance(outlets, list) or len(outlets) == 0:
            print("  ⚠️ Cảnh báo: Dữ liệu tải về trống hoặc không đúng định dạng!")
            sys.exit(1)

        # Ghi vào file local chuẩn UTF-8
        with open(LOCAL_OUTLETS_FILE, "w", encoding="utf-8") as f:
            json.dump(outlets, f, ensure_ascii=False, indent=2)

        file_size_kb = LOCAL_OUTLETS_FILE.stat().st_size / 1024
        print(f"  ✓ Đã ghi thành công {len(outlets)} cửa hàng vào: {LOCAL_OUTLETS_FILE} ({file_size_kb:.1f} KB)")

        # Thử làm mới bộ nhớ OCR engine cục bộ nếu module có sẵn
        try:
            import ocr_engine
            ocr_engine.reload_master_outlets()
            print("  ✓ Đã làm mới cache OCR Engine trên máy Mac!")
        except Exception:
            pass

        print("\n" + "=" * 70)
        print(f"🎉 HOÀN TẤT ĐỒNG BỘ: {len(outlets)} cửa hàng đã sẵn sàng trên máy Mac.")
        print("=" * 70)
    except urllib.error.HTTPError as e:
        print(f"  ❌ Lỗi tải danh mục (HTTP {e.code}): {e.reason}")
        sys.exit(1)
    except Exception as e:
        print(f"  ❌ Lỗi kết nối: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Sync master outlets from Pilot API to local Mac")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Địa chỉ máy chủ API (mặc định: {DEFAULT_HOST})")
    parser.add_argument("--remote-sync", action="store_true", help="Yêu cầu Server đồng bộ từ DB trước khi tải về")
    parser.add_argument("--actor", default="Dev_Mac", help="Tên người/thiết bị yêu cầu đồng bộ")
    args = parser.parse_args()

    sync_outlets_via_api(host=args.host, trigger_remote=args.remote_sync, actor=args.actor)


if __name__ == "__main__":
    main()
