# CHUYÊN ĐỀ 8: ĐỐI CHIẾU MÔI TRƯỜNG & QUY TRÌNH QUẢN LÝ THAY ĐỔI (SERVER BASELINE & CHANGE MANAGEMENT)

> **Mã chuyên đề**: `SPEC-08-CHANGE-MGMT`  
> **Phiên bản tài liệu**: 2.0 (Cập nhật 25/10/2026)  
> **Đối tượng áp dụng**: Tất cả thành viên dự án (AI Dev, Backend, DevOps, Project Manager)

---

## 1. NGUYÊN TẮC BẮT BUỘC QUẢN LÝ THAY ĐỔI (CHANGE MANAGEMENT RULE)

> [!IMPORTANT]
> ### ⚠️ NGUYÊN TẮC BẮT BUỘC CHO MỌI HÀNH ĐỘNG (CHANGE MANAGEMENT RULE)
> **CHO MỌI HÀNH ĐỘNG (chỉnh sửa mã nguồn, cấu hình, database, script hệ thống):**
> 1. **Luôn lập kế hoạch chi tiết (Plan for Review)** trước khi chỉnh sửa bất kỳ dòng mã nguồn hay tệp cấu hình nào. Ghi nhận rõ ràng vào [DEV_PLAN.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_PLAN.md).
> 2. **Chỉ thực hiện sau khi có Review và chấp nhận.**
> 3. **Sử dụng câu lệnh `"OK"` để thể hiện sự đồng ý / phê duyệt.**  
> *(Tuyệt đối không tự ý can thiệp mã nguồn, database hay chạy script tác động hệ thống khi chưa có phản hồi "OK" từ Quản lý / User).*

---

## 2. QUY TRÌNH SONG HÀNH DEV_PLAN.md VÀ DEV_HISTORY.md

Hệ thống duy trì cặp đôi tài liệu quản trị tiến độ và lịch sử thay đổi:
* **[DEV_PLAN.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_PLAN.md)**: Nơi lập Kế hoạch đề xuất (Plan for Review), phân tích mục tiêu kỹ thuật, giải pháp kiến trúc và bảng Checklist hành động chi tiết trước khi bắt tay vào code.
* **[DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md)**: Nơi ghi nhận nhật ký kết quả nghiệm thu thực tế (What was done, Test outcomes, Latency, Error root cause analysis, Key findings) sau khi được User chấp thuận và thực thi thành công.

---

## 3. BẢNG ĐỐI CHIẾU MÔI TRƯỜNG DEV vs PILOT (ENVIRONMENT MATRIX)

| Tiêu chí so sánh | Môi trường DEV (Máy cá nhân Mac) | Môi trường PILOT (Máy chủ Ubuntu) |
| :--- | :--- | :--- |
| **IP / Host** | `127.0.0.1:8000` (`localhost`) | `14.161.34.37:8080` (Public IP) |
| **Phần cứng** | Mac Mini M4, 24GB Unified Memory | Core i7-13700KF, 32GB RAM, RTX 3060 12GB VRAM |
| **Hệ điều hành** | macOS 26.6.2 (Darwin ARM64) | Ubuntu 22.04 LTS (x86_64) |
| **Thư viện AI** | `mlx` (0.32.4) + `mlx-vlm` (0.7.9) | `torch` (2.4.0) + `bitsandbytes` (0.43.3) |
| **Mô hình VLM** | `Qwen2-VL-7B-Instruct-4bit` (MLX local) | `Qwen2-VL-7B-Instruct` (NF4 4-bit CUDA) |
| **Vị trí Cache** | `models/Qwen2-VL-7B-Instruct-4bit/` | `/mnt/data/ocr-bill/cache/huggingface/` |
| **Độ trễ bóc tách**| ~7.5s - 7.8s / hóa đơn | **~3.5s / hóa đơn (Nhanh gấp 2.2 lần)** |
| **Chốt chặn Cron** | **BỊ KHÓA HOÀN TOÀN** (Tự động thoát nếu không có `--force`) | **CHO PHÉP HOẠT ĐỘNG** (Quét 15 phút/lần hoặc ban đêm) |
| **Báo cáo Cron Web**| Khóa an toàn (`HTTP 403 Forbidden`) | Hiển thị đầy đủ lịch sử nhịp tim hệ thống |
| **Quản trị tiến trình**| Chạy foreground terminal (`python app_review.py`) | Chạy background daemon `systemd` (`ocr-bill.service`) |
| **Đồng bộ mã nguồn**| Git local repo `/Volumes/ExternalSSD/ocr-bill` | Nhận qua script CI/CD `deploy_to_pilot.py` |
