"""
Tiến trình quét và bóc tách hóa đơn định kỳ (Cron OCR Scanner)
Dành cho hệ thống CRM Gigamall:
- Quét các hóa đơn ở trạng thái PENDING chưa từng được OCR (OcrLatency is NULL/0)
- Bóc tách tự động bằng Qwen2-VL trên Apple Silicon (hoặc Linux GPU)
- Cập nhật kết quả vào bảng OcrBills và ghi vết OcrBillAuditLogs
- Có thể chạy 1 lần qua crontab hoặc chạy vòng lặp ngầm (Daemon mode)
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
IMAGE_DIR = BASE_DIR / "TEST_IMAGES"

# Nạp môi trường kết nối FreeTDS và DB
os.environ.setdefault("FREETDSCONF", str(BASE_DIR / "freetds.conf"))

import db
import ocr_engine


def find_image_path(filename: str, image_path_db: str = None) -> Path:
    """Xác định đường dẫn file ảnh vật lý trên ổ cứng."""
    clean_name = os.path.basename(filename)
    # 1. Thư mục uploads
    p1 = UPLOAD_DIR / clean_name
    if p1.exists():
        return p1
    # 2. Thư mục theo ImagePath trong DB
    if image_path_db:
        p2 = BASE_DIR / image_path_db
        if p2.exists():
            return p2
    # 3. Thư mục TEST_IMAGES
    p3 = IMAGE_DIR / clean_name
    if p3.exists():
        return p3
    return None


def process_single_bill(bill: dict) -> dict:
    """Xử lý OCR cho 1 hóa đơn và cập nhật CSDL."""
    bill_id = bill["BillId"]
    filename = bill["Filename"]
    img_path = find_image_path(filename, bill.get("ImagePath"))

    if not img_path or not img_path.exists():
        err_msg = f"Không tìm thấy file ảnh trên đĩa cho BillId {bill_id} ({filename})"
        print(f"[-] [Bill #{bill_id}] LỖI: {err_msg}")
        ocr_err = {
            "raw_brand": "",
            "raw_outlet": "",
            "bill_number": "",
            "bill_datetime": None,
            "bill_total": 0,
            "is_valid_bill": False,
            "outlet_number": None,
            "resolved_outlet": None,
            "match_score": 0.0,
            "latency": 0.0,
            "raw_output": err_msg,
        }
        db.update_bill_ocr_result(bill_id, ocr_err)
        return {"bill_id": bill_id, "success": False, "error": err_msg}

    print(f"[*] [Bill #{bill_id}] Bắt đầu bóc tách ảnh: {img_path.name}...")
    t0 = time.time()
    try:
        ocr_res = ocr_engine.process_bill_image(img_path)
        success = True
    except Exception as e:
        success = False
        ocr_res = {
            "raw_brand": "",
            "raw_outlet": "",
            "bill_number": "",
            "bill_datetime": None,
            "bill_total": 0,
            "is_valid_bill": False,
            "outlet_number": None,
            "resolved_outlet": None,
            "match_score": 0.0,
            "latency": round(time.time() - t0, 2),
            "raw_output": f"OCR Error: {str(e)}",
        }

    # Cập nhật kết quả vào CSDL
    db.update_bill_ocr_result(bill_id, ocr_res)

    status_tag = "✅ THÀNH CÔNG" if ocr_res.get("is_valid_bill") else "⚠️ THẤT BẠI/CHỜ DUYỆT TAY"
    print(f"[+] [Bill #{bill_id}] {status_tag} ({ocr_res['latency']}s)")
    if ocr_res.get("resolved_outlet"):
        print(f"    - Quán: {ocr_res['resolved_outlet']} ({ocr_res['outlet_number']}, score={ocr_res['match_score']})")
    if ocr_res.get("bill_total"):
        print(f"    - Tổng tiền: {ocr_res['bill_total']:,} đ | Số bill: {ocr_res['bill_number']}")

    return {"bill_id": bill_id, "success": success, "data": ocr_res}


def scan_and_run(limit: int = 50, dry_run: bool = False, specific_bill_id: int = None) -> list:
    """Quét các bill chưa xử lý và chạy bóc tách."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now_str}] 🔍 Đang quét CSDL tìm hóa đơn chưa bóc tách OCR...")

    if specific_bill_id:
        bills = db.get_bills_by_ids([specific_bill_id])
    else:
        bills = db.get_unprocessed_bills(limit=limit)

    if not bills:
        print("[+] Tuyệt vời! Không có hóa đơn nào tồn đọng cần bóc tách.")
        return []

    print(f"[!] Tìm thấy {len(bills)} hóa đơn cần bóc tách OCR.")
    if dry_run:
        for b in bills:
            print(f"    - BillId: {b['BillId']} | File: {b['Filename']} | Ngày tạo: {b['CreatedAt']}")
        return []

    results = []
    for idx, b in enumerate(bills, 1):
        print(f"\n--- Tiến độ: [{idx}/{len(bills)}] ---")
        res = process_single_bill(b)
        results.append(res)

    print(f"\n[+] Đã hoàn tất đợt bóc tách {len(results)} hóa đơn!")
    return results


def main():
    parser = argparse.ArgumentParser(description="Cron OCR Scanner cho GigaMall CRM")
    parser.add_argument("--limit", type=int, default=50, help="Số lượng bill tối đa quét trong 1 đợt (mặc định: 50)")
    parser.add_argument("--loop", action="store_true", help="Chạy ở chế độ Daemon lặp lại liên tục")
    parser.add_argument("--interval", type=int, default=300, help="Khoảng thời gian nghỉ giữa các đợt quét tính bằng giây (mặc định: 300s = 5 phút)")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra và in danh sách bill cần OCR, không chạy mô hình")
    parser.add_argument("--bill-id", type=int, default=None, help="Chỉ định bóc tách duy nhất 1 BillId")
    parser.add_argument("--sync-outlets", action="store_true", help="Tự động đồng bộ danh mục cửa hàng từ CSDL MS-SQL trước khi quét")

    args = parser.parse_args()

    if args.sync_outlets:
        print("[*] Đang đồng bộ danh mục cửa hàng từ CSDL MS-SQL...")
        try:
            cnt = db.sync_master_outlets_file()
            ocr_engine.reload_master_outlets()
            print(f"[+] Đã đồng bộ {cnt} cửa hàng vào master_outlets.json!")
        except Exception as e:
            print(f"[!] Cảnh báo: Đồng bộ cửa hàng thất bại ({e}), tiếp tục dùng danh mục hiện có.")

    if args.loop:
        print(f"[*] Khởi động Cron OCR Scanner ở chế độ DAEMON (quét mỗi {args.interval} giây)...")
        print("[*] Nhấn Ctrl+C để dừng tiến trình.\n")
        try:
            while True:
                if args.sync_outlets:
                    try:
                        db.sync_master_outlets_file()
                        ocr_engine.reload_master_outlets()
                    except Exception:
                        pass
                scan_and_run(limit=args.limit, dry_run=args.dry_run)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n[!] Đã dừng Cron OCR Scanner.")
    else:
        scan_and_run(limit=args.limit, dry_run=args.dry_run, specific_bill_id=args.bill_id)


if __name__ == "__main__":
    main()
