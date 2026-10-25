# CHUYÊN ĐỀ 2: TỐI ƯU HÓA MÔ HÌNH VLM 7B & TĂNG TỐC GPU NVIDIA RTX 3060 CUDA (VLM MODEL & GPU OPTIMIZATION)

> **Mã chuyên đề**: `SPEC-02-VLM-GPU`  
> **Phiên bản tài liệu**: 2.0 (Cập nhật 25/10/2026)  
> **Đối tượng áp dụng**: AI Engineer, Machine Learning Developer, Performance Engineer, DevOps

---

## 1. BỐI CẢNH & PHÁT HIỆN KỸ THUẬT BAN ĐẦU

### 1.1. Hiện tượng "Empty Result" trên Máy chủ Pilot
Trước ngày 25/10/2026, khi ứng dụng gọi API `/api/v1/extract-bill` trên máy chủ Pilot (`14.161.34.37:8080`), API trả về HTTP 200 nhưng tất cả các trường dữ liệu đều rỗng:
```json
{
  "brand_name": "",
  "outlet_name": "",
  "bill_number": "",
  "bill_datetime": "",
  "bill_total": 0,
  "is_valid_bill": true
}
```

### 1.2. Giải mã Nguyên nhân Cốt lõi
Qua trích xuất log và debug sâu trên GPU NVIDIA:
1. **Khác biệt mô hình**:
   * Máy Dev (Mac Mini M4) chạy mô hình **`Qwen2-VL-7B-Instruct-4bit` (7 Tỷ tham số)** $\rightarrow$ Đọc rất tốt ngữ cảnh tiếng Việt và chi tiết font chữ nhỏ.
   * Máy Pilot cấu hình mặc định là **`Qwen/Qwen2-VL-2B-Instruct` (chỉ 2 Tỷ tham số)**.
2. **Năng lực suy luận của mô hình 2B**:
   * Mô hình 2B quá nhỏ, không đủ năng lực phân giải chữ nhỏ trên ảnh hóa đơn bán lẻ phức tạp.
   * Khi gặp câu Prompt: *"- Trường nào không đọc được thì để chuỗi rỗng (bill_total để 0)"*, mô hình 2B sao chép y nguyên cấu trúc rỗng của prompt và sinh ra JSON rỗng chỉ trong 1.2s.

---

## 2. NÂNG CẤP MÔ HÌNH 7B & TẬN DỤNG TỐI ĐA GPU NVIDIA RTX 3060

### 2.1. Năng lực Phần cứng Máy chủ Pilot
* **GPU**: NVIDIA GeForce RTX 3060 ( kiến trúc Ampere GA106).
* **VRAM**: **12,288 MiB (12GB GDDR6)**.
* **CPU**: Intel Core i7-13700KF (24 vCPUs).
* **Nhận định**: Với 12GB VRAM, máy chủ Pilot hoàn toàn dư sức nạp mô hình 7B lượng hóa 4-bit (chỉ tiêu tốn ~3.8GB - 5.5GB VRAM), còn dư hơn 6GB VRAM cho bộ nhớ ngữ cảnh và xử lý ảnh độ phân giải cao.

### 2.2. Kỹ thuật Lượng hóa 4-bit (NF4) qua BitsAndBytes
Hệ thống sử dụng kỹ thuật lượng hóa NormalFloat4 (NF4) với double quantization:
```python
from transformers import BitsAndBytesConfig, Qwen2VLForConditionalGeneration

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True
)

_model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2-VL-7B-Instruct",
    quantization_config=bnb_config,
    device_map="auto"
)
```

### 2.3. Khắc phục Lỗi Phân vùng Ổ đĩa (`HF_HOME`)
* **Sự cố**: Phân vùng root `/` trên Pilot chỉ có 42GB và đã đầy (còn dưới 1.2GB trống), dẫn đến lỗi `Not enough free disk space to download shard (3.8GB)`.
* **Giải pháp**: Tận dụng phân vùng `/mnt/data` (932GB trống), chuyển toàn bộ cache tải mô hình HuggingFace sang `/mnt/data/ocr-bill/cache/huggingface`:
  ```python
  if "HF_HOME" not in os.environ and Path("/mnt/data/ocr-bill/cache/huggingface").exists():
      os.environ["HF_HOME"] = "/mnt/data/ocr-bill/cache/huggingface"
  ```
  Tải trọn vẹn 5/5 shards (~15GB) của mô hình 7B vào phân vùng lưu trữ bền vững.

---

## 3. TỐI ƯU HÓA ĐỘ TRỄ SUY LUẬN (LATENCY OPTIMIZATION)

### 3.1. So sánh Hiệu năng Trước và Sau Tối ưu

| Chỉ số đo lường | Trước tối ưu (Pilot 2B) | Sau tối ưu (Dev Mac M4 - 7B) | Sau tối ưu (Pilot RTX 3060 - 7B) |
| :--- | :---: | :---: | :---: |
| **Mô hình VLM** | Qwen2-VL-2B (2 Tỷ) | Qwen2-VL-7B (7 Tỷ) | **Qwen2-VL-7B (7 Tỷ NF4)** |
| **Tỷ lệ bóc tách thành công** | 0% (Empty JSON) | 100% | **100%** |
| **Tự động khớp Master Outlets**| 0% | 96% - 100% | **96% - 100%** |
| **Thời gian nạp VRAM ban đầu** | ~86 giây | ~5.3 giây | ~215 giây (chỉ 1 lần duy nhất) |
| **Độ trễ bóc tách / hóa đơn** | 1.2s (rác rỗng) | **~7.5 - 7.8 giây** | **~3.5 - 3.6 giây (Nhanh gấp 2.2x)** |
| **Tiêu hao VRAM / Memory** | 2.8GB VRAM | 4.4GB Unified RAM | **3.8GB / 12GB VRAM (An toàn)** |

### 3.2. Cấu hình Kích thước Ảnh & AutoProcessor Thích ứng
* Giới hạn cạnh dài ảnh tối đa `MAX_IMAGE_SIDE = 1600px` kết hợp xoay EXIF tự động (`ImageOps.exif_transpose`).
* Cấu hình AutoProcessor thích ứng theo đúng khuyến nghị của Alibaba Qwen-VL:
  ```python
  _processor = AutoProcessor.from_pretrained(
      model_id,
      min_pixels=256 * 28 * 28,  # ~200,704 pixels (đảm bảo độ sắc nét ký tự nhỏ)
      max_pixels=1280 * 28 * 28  # ~1,003,520 pixels (kiểm soát tốc độ và token visual)
  )
  ```

---

## 4. CHIẾN LƯỢC QUẢN TRỊ BỘ NHỚ VRAM & DỊCH VỤ DÀI HẠN

1. **Thường trú VRAM (Resident Model Pattern)**:
   * Mô hình chỉ nạp 1 lần duy nhất khi khởi động hoặc ở request đầu tiên.
   * Suốt vòng đời của tiến trình `uvicorn`, mô hình luôn thường trú trong VRAM của RTX 3060, giữ cho mọi request tiếp theo đạt độ trễ cực nhanh **~3.5 giây**.
2. **Cơ chế chống lặp token (Repetition Penalty)**:
   * Áp dụng `repetition_penalty = 1.1`, `temperature = 0.01` và `do_sample = False` trong `model.generate()`.
   * Loại bỏ triệt để hiện tượng mô hình sinh lặp vô tận chuỗi số bill (ví dụ: `1100000000...`), giảm tải token và tránh tràn thời gian xử lý.
