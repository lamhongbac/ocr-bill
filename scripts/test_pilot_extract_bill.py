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

PILOT_API_URL = "http://14.161.34.37:8080/api/v1/extract-bill"

def test_pilot_extract():
    print("=" * 85)
    print("🚀 GỌI TEST THỰC NGHIỆM TRỰC TIẾP TỚI SERVER PILOT (14.161.34.37:8080)")
    print(f"API Target: {PILOT_API_URL}")
    print("=" * 85)
    
    results = []
    
    for i, img_path in enumerate(SAMPLE_IMAGES, start=1):
        if not img_path.exists():
            print(f"❌ Không tìm thấy: {img_path}")
            continue
            
        file_size_kb = round(img_path.stat().st_size / 1024, 1)
        print(f"\n--- [Pilot Test #{i}] Đang upload: {img_path.name} ({file_size_kb} KB) ---")
        
        t0 = time.time()
        with open(img_path, "rb") as f:
            files = {"file": (img_path.name, f, "image/png")}
            data = {
                "mem_id": f"PILOT_CRM_{i:02d}",
                "image_number": img_path.stem,
                "duplicate_action": "allow"
            }
            try:
                resp = requests.post(PILOT_API_URL, files=files, data=data, timeout=90)
                client_latency = round(time.time() - t0, 2)
            except Exception as e:
                print(f"❌ Lỗi kết nối tới Pilot: {e}")
                results.append({
                    "sample": img_path.name,
                    "status_code": 0,
                    "client_latency": round(time.time() - t0, 2),
                    "error": str(e)
                })
                continue
                
        print(f"📡 Status Code: {resp.status_code} | Client Latency: {client_latency}s")
        if resp.status_code == 200:
            body = resp.json()
            data_field = body.get("data") or {}
            print(f"  • Success: {body.get('success')}")
            print(f"  • Bill ID trên Pilot: #{body.get('bill_id')}")
            print(f"  • Pilot Latency: {body.get('latency_seconds')}s")
            print(f"  • Brand: '{data_field.get('brand_name')}'")
            print(f"  • Outlet Raw: '{data_field.get('outlet_name')}'")
            print(f"  • Cửa hàng Master: {data_field.get('outlet_number')} ({data_field.get('resolved_outlet')})")
            print(f"  • Điểm so khớp: {data_field.get('match_score')}")
            print(f"  • Tổng tiền: {data_field.get('bill_total'):,} đ")
            print(f"  • Số HĐ: '{data_field.get('bill_number')}'")
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
                "raw_output": body.get("raw_output")
            })
        else:
            print(f"❌ Lỗi Pilot ({resp.status_code}): {resp.text}")
            results.append({
                "sample": img_path.name,
                "status_code": resp.status_code,
                "client_latency": client_latency,
                "error": resp.text
            })
            
    print("\n" + "=" * 85)
    print("📋 BẢNG TỔNG HỢP KẾT QUẢ THỰC NGHIỆM TRÊN PILOT")
    print("=" * 85)
    for r in results:
        if r.get("status_code") == 200:
            d = r["data"]
            print(f"[{r['sample']}] Bill #{r['bill_id']} | Pilot Latency: {r['backend_latency']}s | Total: {d.get('bill_total'):,} đ | Outlet: '{d.get('outlet_name')}' -> {d.get('resolved_outlet')} ({d.get('match_score')}) | BillNo: {d.get('bill_number')}")
        else:
            print(f"[{r['sample']}] FAILED (Status: {r.get('status_code')}) | Error: {r.get('error')}")

if __name__ == "__main__":
    test_pilot_extract()
