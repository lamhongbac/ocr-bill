# CHUYÊN ĐỀ 6: TÁC VỤ QUÉT NGẦM CRON & ĐỒNG BỘ CSDL TỰ ĐỘNG (CRON SCANNER & SYNC OPERATIONS)

> **Mã chuyên đề**: `SPEC-06-CRON-SYNC`  
> **Phiên bản tài liệu**: 2.0 (Cập nhật 25/10/2026)  
> **Đối tượng áp dụng**: System Administrator, DevOps Engineer, Backend Developer

---

## 1. TIẾN TRÌNH QUÉT HÓA ĐƠN ĐỘC LẬP (`cron_ocr_scanner.py`)

Tệp `cron_ocr_scanner.py` là một tiến trình CLI độc lập với Web API, giải quyết 2 bài toán vận hành sống còn:
1. **Chống thất lạc hóa đơn**: Tự động tìm và bóc tách các hóa đơn bị dở dang (ví dụ: client gửi ảnh qua chế độ Fast Save nhưng server bị restart đột ngột trước khi hoàn tất OCR).
2. **Gom tải ban đêm (Nightly Batch Processing)**: Thực hiện quét toàn bộ ảnh hóa đơn tồn đọng vào khung giờ thấp điểm (23:00 - 05:00) để không chiếm dụng GPU trong giờ kinh doanh cao điểm của TTTM.

---

## 2. CHỐT CHẶN AN TOÀN TRÊN MÔI TRƯỜNG DEV (DEV ENVIRONMENT GUARD)

* **Nguyên tắc an toàn**: Để tránh tình trạng script Cron tự động chạy ngầm trên máy cá nhân của Developer làm xung đột dữ liệu hoặc gửi request liên tục vào CSDL, cả 2 script [sync_outlets.py](file:///Volumes/ExternalSSD/ocr-bill/sync_outlets.py) và [cron_ocr_scanner.py](file:///Volumes/ExternalSSD/ocr-bill/cron_ocr_scanner.py) đều được trang bị **chốt chặn môi trường nghiêm ngặt**:
  ```python
  cfg = db.load_db_config()
  env_name = cfg.get("_active_env", "dev").lower()
  if env_name == "dev" and not args.force:
      print("⚠️ CHỐT CHẶN AN TOÀN: Môi trường DEV bị vô hiệu hóa Cron tự động!")
      print("👉 Để chạy thử trên Dev, vui lòng thêm cờ: --force")
      sys.exit(0)
  ```
* **Ý nghĩa**: Trên máy Dev, script lập tức in cảnh báo và thoát với mã 0 nếu không có cờ `--force`.

---

## 3. CÁC LỆNH VẬN HÀNH THƯỜNG DÙNG

```bash
# 1. Kiểm tra nhanh số lượng hóa đơn chưa được OCR (không tốn tài nguyên GPU)
python cron_ocr_scanner.py --dry-run

# 2. Chạy quét bóc tách 1 lô tối đa 50 hóa đơn
python cron_ocr_scanner.py --limit 50

# 3. Chạy chế độ DAEMON lặp lại liên tục (quét mỗi 15 phút = 900s)
python cron_ocr_scanner.py --loop --interval 900

# 4. Chỉ định bóc tách duy nhất 1 hóa đơn cụ thể (Debug)
python cron_ocr_scanner.py --bill-id 105

# 5. Bỏ qua chốt chặn môi trường để chạy thử nghiệm trên máy Dev
python cron_ocr_scanner.py --limit 5 --force
```

---

## 4. BÁO CÁO GIÁM SÁT CRON DÀNH CHO ADMIN (`GET /api/v1/admin/cron-report`)

### 4.1. Cơ chế Lưu vết Lịch sử
Mỗi đợt quét của `cron_ocr_scanner.py` tự động ghi nhận vào `cron_scanner_history.json`:
* Thời điểm bắt đầu và kết thúc (`started_at`, `finished_at`).
* Tổng số hóa đơn phát hiện, số hóa đơn thành công, số hóa đơn lỗi.
* Độ trễ trung bình và tổng thời gian chạy đợt quét.

### 4.2. API Báo cáo Tổng hợp (Chỉ khả dụng trên Pilot & Prod)
* **Endpoint**: `GET /api/v1/admin/cron-report`
* **Cơ chế phân quyền môi trường**:
  * Nếu gọi trên môi trường `DEV`: Trả về `HTTP 403 Forbidden` kèm thông báo: *"Báo cáo Cron chỉ khả dụng trên Pilot và Production"*.
  * Nếu gọi trên `PILOT` hoặc `PROD`: Trả về toàn bộ nhịp tim hệ thống (Health Status), thống kê tỷ lệ thành công 24 giờ và danh sách 10 đợt quét gần nhất.

---

## 5. TỰ ĐỘNG ĐỒNG BỘ DANH MỤC CỬA HÀNG (`POST /api/v1/sync-outlets`)

* **Nguồn dữ liệu**: Bảng `G_Outlet` JOIN `G_Brand` trên CSDL MS-SQL.
* **Câu lệnh SQL trích xuất 193 cửa hàng hợp lệ**:
  ```sql
  SELECT o.ID, o.Number, o.OutletName, b.ID, b.Number, b.BrandName, o.Address
  FROM G_Outlet o WITH (NOLOCK)
  INNER JOIN G_Brand b WITH (NOLOCK) ON o.BrandID = b.ID
  WHERE ISNULL(o.IsActive, 1) = 1 AND ISNULL(o.IsUsed, 1) = 1
  ORDER BY o.OutletName;
  ```
* **Cơ chế Hot-Reload**:
  * Khi gọi `POST /api/v1/sync-outlets`, hệ thống ghi đè file [master_outlets.json](file:///Volumes/ExternalSSD/ocr-bill/master_outlets.json) chuẩn UTF-8 và gọi hàm `ocr_engine.reload_master_outlets()` để làm mới cache bộ nhớ RAM mà không cần restart tiến trình uvicorn.
