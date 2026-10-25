import requests
import json
import time
from pathlib import Path

SAMPLE_IMAGES = [
    Path("/Volumes/ExternalSSD/temp/100926/OCR/10852_100926222127.png"),
    Path("/Volumes/ExternalSSD/temp/100926/OCR/909_100926200240.png"),
    Path("/Volumes/ExternalSSD/temp/100926/OCR/13747_100926104559.png"),
    Path("/Volumes/ExternalSSD/temp/100926/OCR/44973_100926225318.png"),
]

API_URL = "http://127.0.0.1:8000/api/v1/extract-bill"

def run_demo():
    print("=" * 80)
    print("🚀 BẮT ĐẦU CHẠY DEMO & ĐÁNH GIÁ API: POST /api/v1/extract-bill")
    print("=" * 80)
    
    results = []
    
    for i, img_path in enumerate(SAMPLE_IMAGES, start=1):
        if not img_path.exists():
            print(f"❌ Không tìm thấy file: {img_path}")
            continue
            
        file_size_kb = round(img_path.stat().st_size / 1024, 1)
        print(f"\n--- [Test #{i}] Đang gửi ảnh: {img_path.name} ({file_size_kb} KB) ---")
        
        t0 = time.time()
        with open(img_path, "rb") as f:
            files = {"file": (img_path.name, f, "image/png")}
            data = {
                "mem_id": f"MEM_TEST_{i:02d}",
                "image_number": img_path.stem,
                "duplicate_action": "allow"  # cho phép để luôn chạy OCR ngay cả khi ảnh trùng
            }
            try:
                resp = requests.post(API_URL, files=files, data=data, timeout=60)
                client_latency = round(time.time() - t0, 2)
            except Exception as e:
                print(f"❌ Lỗi gửi request: {e}")
                results.append({
                    "sample": img_path.name,
                    "status_code": 0,
                    "client_latency": round(time.time() - t0, 2),
                    "error": str(e)
                })
                continue
                
        print(f"📡 Status Code: {resp.status_code} | Tổng thời gian (client): {client_latency}s")
        if resp.status_code == 200:
            body = resp.json()
            data_field = body.get("data") or {}
            raw_output = body.get("raw_output")
            
            print(f"  • Success: {body.get('success')}")
            print(f"  • Bill ID: #{body.get('bill_id')}")
            print(f"  • Backend Latency: {body.get('latency_seconds')}s")
            print(f"  • Thương hiệu (Brand): '{data_field.get('brand_name')}'")
            print(f"  • Tên quán (Outlet): '{data_field.get('outlet_name')}'")
            print(f"  • Mã cửa hàng Master: {data_field.get('outlet_number')} ({data_field.get('resolved_outlet')})")
            print(f"  • Điểm so khớp mờ: {data_field.get('match_score')}")
            print(f"  • Tổng tiền (Total): {data_field.get('bill_total'):,} đ")
            print(f"  • Số hóa đơn: '{data_field.get('bill_number')}'")
            print(f"  • Ngày giờ: '{data_field.get('bill_datetime')}'")
            print(f"  • Hợp lệ: {data_field.get('is_valid_bill')}")
            
            results.append({
                "sample": img_path.name,
                "file_size_kb": file_size_kb,
                "status_code": resp.status_code,
                "client_latency": client_latency,
                "backend_latency": body.get("latency_seconds"),
                "success": body.get("success"),
                "bill_id": body.get("bill_id"),
                "data": data_field,
                "raw_output": raw_output
            })
        else:
            print(f"❌ Server Error ({resp.status_code}): {resp.text}")
            results.append({
                "sample": img_path.name,
                "status_code": resp.status_code,
                "client_latency": client_latency,
                "error": resp.text
            })
            
    print("\n" + "=" * 80)
    print("📋 BẢNG TỔNG HỢP KẾT QUẢ DEMO")
    print("=" * 80)
    for r in results:
        if r["status_code"] == 200:
            d = r["data"]
            print(f"[{r['sample']}] Bill #{r['bill_id']} | Latency: {r['client_latency']}s | Total: {d.get('bill_total'):,} đ | Brand: '{d.get('brand_name')}' | Outlet: '{d.get('outlet_name')}' -> {d.get('resolved_outlet')} ({d.get('match_score')}) | BillNo: {d.get('bill_number')}")
        else:
            print(f"[{r['sample']}] FAILED (Status: {r['status_code']}) | Error: {r.get('error')}")

if __name__ == "__main__":
    run_demo()
