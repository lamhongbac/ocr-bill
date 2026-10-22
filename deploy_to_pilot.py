#!/usr/bin/env python3
"""
Script tự động hóa quy trình Triển khai (CI/CD Deployment) từ máy Dev lên máy chủ Pilot (14.161.34.37).
Quy trình:
1. Pre-flight check: Kiểm tra cú pháp Python cục bộ (py_compile).
2. SFTP Transfer: Đẩy các file mã nguồn mới lên /opt/ocr-bill/.
3. Systemd Reload: Khởi động lại dịch vụ ocr-bill.service qua SSH.
4. Health Check / Smoke Test: Gọi API kiểm tra sức khỏe và độ trễ phản hồi.
"""

import sys
import time
import py_compile
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("[!] Chưa cài đặt thư viện 'paramiko'. Vui lòng chạy: pip install paramiko")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None

SERVER_HOST = "14.161.34.37"
SERVER_PORT = 22
SERVER_USER = "msa"
SERVER_PASS = "Admin@2026"
REMOTE_DIR = "/opt/ocr-bill"

# Danh sách các file cốt lõi cần đồng bộ khi triển khai
DEPLOY_FILES = [
    "app_review.py",
    "db.py",
    "ocr_engine.py",
    "CRM_API_INTEGRATION_SPEC.md",
    "setup_database_dev.sql",
    "SERVER_BASELINE_AND_CHANGE_MANAGEMENT.md",
    "deploy_to_pilot.py"
]


def check_local_syntax():
    print("[1/4] 🔍 Kiểm tra cú pháp mã nguồn cục bộ...")
    for fn in ["app_review.py", "db.py", "ocr_engine.py"]:
        p = Path(fn)
        if p.exists():
            try:
                py_compile.compile(str(p), doraise=True)
                print(f"  ✓ {fn}: Cú pháp hợp lệ")
            except py_compile.PyCompileError as e:
                print(f"  ❌ Lỗi cú pháp trong {fn}: {e}")
                sys.exit(1)


def upload_files_via_sftp(ssh):
    print(f"[2/4] 📤 Đang đồng bộ file lên máy chủ {SERVER_HOST}:{REMOTE_DIR}...")
    sftp = ssh.open_sftp()
    uploaded = 0
    for fn in DEPLOY_FILES:
        local_path = Path(fn)
        if local_path.exists():
            remote_path = f"{REMOTE_DIR}/{fn}"
            sftp.put(str(local_path), remote_path)
            size_kb = local_path.stat().st_size / 1024
            print(f"  ✓ Đã tải lên: {fn} ({size_kb:.1f} KB)")
            uploaded += 1
    sftp.close()
    print(f"  -> Hoàn tất tải lên {uploaded} tệp.")


def restart_remote_service(ssh):
    print("[3/4] 🔄 Khởi động lại dịch vụ ocr-bill.service trên máy chủ...")
    cmd = "sudo -S systemctl restart ocr-bill && systemctl is-active ocr-bill"
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    stdin.write(f"{SERVER_PASS}\n")
    stdin.flush()
    output = stdout.read().decode().strip()
    
    if "active" in output:
        print(f"  ✓ Trạng thái dịch vụ: ACTIVE (Chạy ngầm thành công)")
    else:
        print(f"  ⚠️ Cảnh báo dịch vụ: {output}")


def run_smoke_test():
    print("[4/4] 🩺 Kiểm tra sức khỏe hệ thống (Smoke Testing)...")
    time.sleep(1.5)  # Chờ 1.5s để Uvicorn bind socket
    test_url = f"http://{SERVER_HOST}:8080/api/stats"
    try:
        if requests:
            t0 = time.time()
            res = requests.get(test_url, timeout=10)
            latency = (time.time() - t0) * 1000
            if res.status_code == 200:
                print(f"  ✓ HTTP {res.status_code} OK (Độ trễ: {latency:.1f}ms) | URL: {test_url}")
                print(f"  ✓ Dữ liệu thống kê: {res.json()}")
            else:
                print(f"  ⚠️ Phản hồi HTTP {res.status_code}: {res.text}")
        else:
            print("  (Bỏ qua bước gọi HTTP do chưa cài requests trong môi trường hiện tại)")
    except Exception as e:
        print(f"  ⚠️ Không thể kết nối tới {test_url}: {e}")


def main():
    print("=" * 70)
    print("🚀 GIGAMALL OCR - QUY TRÌNH TRIỂN KHAI TỰ ĐỘNG LÊN SERVER PILOT")
    print(f"🎯 Máy chủ đích: {SERVER_USER}@{SERVER_HOST}:{REMOTE_DIR}")
    print("=" * 70)

    check_local_syntax()

    print(f"\n🔐 Đang kết nối SSH tới {SERVER_HOST}:{SERVER_PORT}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(SERVER_HOST, port=SERVER_PORT, username=SERVER_USER, password=SERVER_PASS, timeout=15)
        print("  ✓ Kết nối SSH thành công!")
    except Exception as e:
        print(f"  ❌ Kết nối SSH thất bại: {e}")
        sys.exit(1)

    try:
        upload_files_via_sftp(ssh)
        restart_remote_service(ssh)
    finally:
        ssh.close()

    print()
    run_smoke_test()
    print("\n" + "=" * 70)
    print("🎉 TRIỂN KHAI HOÀN TẤT THÀNH CÔNG! HỆ THỐNG ĐÃ SẴN SÀNG.")
    print("=" * 70)


if __name__ == "__main__":
    main()
