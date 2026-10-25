"""
Module OCR Engine cho GigaMall CRM
Nạp mô hình Qwen2-VL-7B-Instruct-4bit trên Mac Mini (Apple Silicon / Metal)
Hỗ trợ bóc tách hóa đơn trực tiếp cho API upload từ Mobile / CRM
"""
import difflib
import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent
if "HF_HOME" not in os.environ and Path("/mnt/data/ocr-bill/cache/huggingface").exists():
    os.environ["HF_HOME"] = "/mnt/data/ocr-bill/cache/huggingface"
MASTER_OUTLETS_FILE = BASE_DIR / "master_outlets.json"
LOCAL_MODEL_DIR = BASE_DIR / "models" / "Qwen2-VL-7B-Instruct-4bit"
HF_MODEL_ID = "mlx-community/Qwen2-VL-7B-Instruct-4bit"
TEMP_WORK_DIR = BASE_DIR / ".work"

MAX_IMAGE_SIDE = 1600
MATCH_CUTOFF = 0.6

EXTRACTION_PROMPT = """Bạn là chuyên gia bóc tách hóa đơn tại Trung tâm Thương mại Gigamall.
Hãy đọc ảnh hóa đơn và chỉ trả về MỘT đối tượng JSON duy nhất (không markdown, không giải thích) theo mẫu:
{
  "brand_name": "Tên thương hiệu (nếu có, nếu không thì chuỗi rỗng)",
  "outlet_name": "Tên cửa hàng in trên hóa đơn",
  "bill_number": "Mã số hóa đơn / Bill No / Số HĐ",
  "bill_datetime": "Ngày giờ giao dịch dạng YYYY-MM-DD HH:mm:ss",
  "bill_total": 0,
  "is_valid_bill": true
}
Quy tắc:
- ĐỊNH DẠNG SỐ TIỀN (VIỆT NAM ĐỒNG - VND):
  * Hóa đơn tại Việt Nam dùng dấu chấm '.' hoặc phẩy ',' phân cách hàng nghìn (ví dụ: '75.000' hay '75,000' là 75 nghìn đồng -> phải ghi số nguyên 75000; '204.000' -> ghi 204000; '200.000' -> ghi 200000; '1.500.000' -> ghi 1500000).
  * Luôn ghi đầy đủ tất cả các chữ số nguyên, tuyệt đối không bỏ các số 0 hàng nghìn và không ghi số thập phân (không được ghi 75 hay 204).
  * Không ghi đơn vị tiền tệ (đ, VND), không ghi dấu chấm phẩy trong số bill_total.
- bill_total là số tiền CUỐI CÙNG khách thực trả (Tổng thanh toán / Khách phải trả / Total due / Net Amount) SAU khi đã trừ giảm giá, voucher, điểm. Không lấy tiền giảm giá, không lấy tiền khách đưa, không lấy tiền thối lại.
- is_valid_bill = false nếu ảnh không phải hóa đơn mua hàng, hoặc quá mờ không đọc được thông tin.
- Trường nào không đọc được thì để chuỗi rỗng (bill_total để 0)."""


# Singleton cache for Model & Processor
_model = None
_processor = None
_config = None
_model_lock = threading.Lock()

# Cached master outlets
_master_outlets = None
_outlet_index = None


def normalize(text):
    """Bỏ dấu tiếng Việt, ký tự đặc biệt, viết hoa để so khớp mờ."""
    if not text:
        return ""
    text = str(text).replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
    return re.sub(r"\s+", " ", text).strip()


def get_outlet_index():
    global _master_outlets, _outlet_index
    if _outlet_index is not None:
        return _outlet_index

    if not MASTER_OUTLETS_FILE.exists():
        _outlet_index = []
        return _outlet_index

    with open(MASTER_OUTLETS_FILE, "r", encoding="utf-8-sig") as f:
        _master_outlets = json.load(f)

    index = []
    for o in _master_outlets:
        keys = {normalize(o.get("outlet_name")), normalize(o.get("outlet_number"))}
        brand = normalize(o.get("brand_name"))
        if brand:
            keys.add(brand)
        index.append((o, {k for k in keys if k}))

    _outlet_index = index
    return _outlet_index


def reload_master_outlets():
    """Xóa cache bộ nhớ và nạp lại danh mục cửa hàng từ master_outlets.json."""
    global _master_outlets, _outlet_index
    _master_outlets = None
    _outlet_index = None
    return get_outlet_index()


def _score(candidate, key):
    if not candidate or not key:
        return 0.0
    if candidate == key:
        return 1.0
    short, long_ = sorted((candidate, key), key=len)
    if len(short) >= 4 and re.search(rf"\b{re.escape(short)}\b", long_):
        return 0.9
    return difflib.SequenceMatcher(None, candidate, key).ratio()


def resolve_outlet(raw_outlet, raw_brand, return_candidates: bool = False, top_n: int = 3):
    """
    So khớp mờ tên quán và thương hiệu với danh mục Master Outlets.
    Trả về (outlet_number, outlet_name, match_score) hoặc kèm top_candidates nếu return_candidates=True.
    """
    outlet_index = get_outlet_index()
    candidates = [c for c in {normalize(raw_outlet), normalize(raw_brand)} if c]
    if not candidates or not outlet_index:
        if return_candidates:
            return None, None, 0.0, []
        return None, None, 0.0

    ranked = []
    for obj, keys in outlet_index:
        best_s = 0.0
        for cand in candidates:
            for key in keys:
                s = _score(cand, key)
                if s > best_s:
                    best_s = s
        if best_s > 0:
            ranked.append({
                "outlet_number": obj.get("outlet_number"),
                "outlet_name": obj.get("outlet_name"),
                "brand_name": obj.get("brand_name"),
                "outlet_address": obj.get("outlet_address"),
                "score": round(best_s, 2),
                "score_pct": int(round(best_s * 100))
            })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = ranked[:top_n]

    if top_candidates and top_candidates[0]["score"] >= MATCH_CUTOFF:
        best = top_candidates[0]
        if return_candidates:
            return best["outlet_number"], best["outlet_name"], best["score"], top_candidates
        return best["outlet_number"], best["outlet_name"], best["score"]

    best_score = top_candidates[0]["score"] if top_candidates else 0.0
    if return_candidates:
        return None, None, round(best_score, 2), top_candidates
    return None, None, round(best_score, 2)


def resolve_outlet_debug(raw_outlet: str, raw_brand: str, top_n: int = 5) -> dict:
    """Hàm tiện ích Debug: Trả về chi tiết các ứng viên và giải thích kết quả so khớp."""
    out_num, out_name, score, top_cands = resolve_outlet(raw_outlet, raw_brand, return_candidates=True, top_n=top_n)
    return {
        "raw_outlet": raw_outlet,
        "raw_brand": raw_brand,
        "is_matched": out_name is not None,
        "resolved_outlet_number": out_num,
        "resolved_outlet_name": out_name,
        "match_score": score,
        "match_cutoff": MATCH_CUTOFF,
        "top_candidates": top_cands
    }


_device = None

def get_model():
    """Tải model vào Unified Memory (Apple Silicon) hoặc VRAM (NVIDIA GPU) một lần duy nhất."""
    global _model, _processor, _config, _device
    if _model is not None:
        return _model, _processor, _config, _device

    with _model_lock:
        if _model is not None:
            return _model, _processor, _config, _device

        # 1. Kiểm tra môi trường NVIDIA GPU (Linux / Windows)
        try:
            import torch
            if torch.cuda.is_available():
                from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
                model_id = os.getenv("OCR_MODEL_ID", "Qwen/Qwen2-VL-7B-Instruct")
                gpu_name = torch.cuda.get_device_name(0)
                print(f"[*] [OCR Engine] Phát hiện NVIDIA GPU ({gpu_name}). Đang nạp {model_id} (7B 4-bit) qua PyTorch CUDA...")
                t0 = time.time()
                
                # Cố gắng nạp 4-bit qua bitsandbytes nếu có để tiết kiệm VRAM (<6GB)
                try:
                    from transformers import BitsAndBytesConfig
                    bnb_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True
                    )
                    _model = Qwen2VLForConditionalGeneration.from_pretrained(
                        model_id,
                        quantization_config=bnb_config,
                        device_map="auto"
                    )
                except Exception as bnb_err:
                    print(f"[*] [OCR Engine] Nạp chuẩn float16: {bnb_err}")
                    _model = Qwen2VLForConditionalGeneration.from_pretrained(
                        model_id,
                        torch_dtype=torch.float16,
                        device_map="auto"
                    )
                _processor = AutoProcessor.from_pretrained(model_id, min_pixels=256*28*28, max_pixels=1280*28*28)
                _config = _model.config
                _device = "cuda"
                print(f"[+] [OCR Engine] Đã nạp xong mô hình 7B lên NVIDIA GPU trong {time.time() - t0:.2f}s!")
                return _model, _processor, _config, _device
        except Exception as e:
            print(f"[*] [OCR Engine] Bỏ qua CUDA ({e}), thử kiểm tra Apple Silicon...")

        # 2. Môi trường Apple Silicon (macOS Metal / MLX)
        from mlx_vlm import load
        from mlx_vlm.utils import load_config

        model_ref = str(LOCAL_MODEL_DIR) if (LOCAL_MODEL_DIR / "config.json").exists() else HF_MODEL_ID
        print(f"[*] [OCR Engine] Đang tải mô hình {model_ref} vào Apple Silicon Unified Memory...")
        t0 = time.time()
        _model, _processor = load(model_ref)
        _config = load_config(model_ref)
        _device = "mlx"
        print(f"[+] [OCR Engine] Đã nạp xong mô hình trong {time.time() - t0:.2f}s!")
        return _model, _processor, _config, _device


def parse_model_json(text):
    """Parse JSON kết quả VLM với cơ chế regex fallback."""
    if not text:
        raise ValueError("Model trả về output rỗng")
    clean = text.replace("```json", "").replace("```", "").strip()
    start = clean.find("{")
    if start != -1:
        end = clean.rfind("}")
        if end > start:
            try:
                return json.loads(clean[start:end + 1])
            except Exception:
                pass

    # Regex fallback
    data = {}
    for key in ["brand_name", "outlet_name", "bill_number", "bill_datetime"]:
        m = re.search(rf'"{key}"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean)
        if m:
            data[key] = m.group(1)
    m_total = re.search(r'"bill_total"\s*:\s*([0-9.,]+)', clean)
    if m_total:
        data["bill_total"] = m_total.group(1)
    m_valid = re.search(r'"is_valid_bill"\s*:\s*(true|false)', clean, re.IGNORECASE)
    if m_valid:
        data["is_valid_bill"] = m_valid.group(1).lower() == "true"

    if data:
        return data
    raise ValueError(f"Không thể parse JSON từ kết quả mô hình: {clean[:200]}")


def to_int_amount(value, raw_str: str = None):
    if value is None or isinstance(value, bool):
        return 0
    num = 0
    if isinstance(value, (int, float)):
        num = int(round(value))
    else:
        s = str(value).strip()
        s = re.sub(r"[^\d.,]", "", s)
        if re.search(r"[.,]\d{3}$", s):
            digits = re.sub(r"[^\d]", "", s)
            num = int(digits) if digits else 0
        elif re.search(r"[.,]\d{2}$", s):
            base = re.sub(r"[.,]\d{2}$", "", s)
            digits = re.sub(r"[^\d]", "", base)
            num = int(digits) if digits else 0
        else:
            digits = re.sub(r"[^\d]", "", s)
            num = int(digits) if digits else 0

    # Chuẩn hóa nếu mô hình hiểu nhầm dấu chấm phân tách hàng nghìn thành số thập phân:
    # Ví dụ: bill_total = 75 hoặc 75.0 (tương ứng 75.000 đ), 204 (204.000 đ), 200 (200.000 đ)
    # Trong TTTM Gigamall, các giao dịch thanh toán F&B/bán lẻ tối thiểu từ 1.000 đ trở lên
    if 0 < num < 1000:
        num = num * 1000

    return num


def prepare_image(img_path: Path) -> Path:
    """Tự động xoay ảnh theo EXIF, resize cạnh dài tối đa 1600px để kiểm soát RAM & tốc độ."""
    TEMP_WORK_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if max(im.size) > MAX_IMAGE_SIDE:
            im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        out_path = TEMP_WORK_DIR / f"prep_{img_path.stem}.jpg"
        im.save(out_path, "JPEG", quality=92)
    return out_path


def optimize_bill_number(raw_bill_number: str, bill_datetime: str = None) -> str:
    """
    Rule 4: Optimize số Hóa đơn:
    - Lấy 6 số cuối của hóa đơn
    - Nếu hóa đơn không đủ 6 số thì tự động thêm số 0 ở đầu cho đủ 6 số (zfill)
    - Nếu không có số HĐ thì lấy ngày giờ làm số HĐ
    """
    raw_digits = re.sub(r"[^0-9]", "", str(raw_bill_number or ""))
    if raw_digits:
        if len(raw_digits) >= 6:
            return raw_digits[-6:]
        else:
            return raw_digits.zfill(6)

    # Nếu không có số HD, lấy chuỗi ngày giờ
    dt_digits = re.sub(r"[^0-9]", "", str(bill_datetime or ""))
    if dt_digits:
        return dt_digits
    return datetime.now().strftime("%Y%m%d%H%M%S")


def process_bill_image(image_path: Path) -> dict:
    """
    Thực hiện xử lý bóc tách toàn diện một ảnh hóa đơn:
    1. Tiền xử lý ảnh (xoay EXIF, resize)
    2. Chạy mô hình Qwen2-VL qua MLX
    3. Phân tích kết quả JSON
    4. So khớp mờ với danh mục 81 cửa hàng CRM
    """
    start_time = time.time()
    model, processor, config, device = get_model()

    prep_img = prepare_image(image_path)
    try:
        if device == "cuda":
            import torch
            from qwen_vl_utils import process_vision_info

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": str(prep_img)},
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }
            ]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            ).to("cuda")

            with torch.no_grad():
                generated_ids = model.generate(
                    **inputs,
                    max_new_tokens=384,
                    repetition_penalty=1.1,
                    temperature=0.01,
                    do_sample=False,
                )
                generated_ids_trimmed = [
                    out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
                ]
                output_texts = processor.batch_decode(
                    generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
                )
                raw_text = output_texts[0].strip()
        else:
            from mlx_vlm import generate
            from mlx_vlm.prompt_utils import apply_chat_template

            prompt = apply_chat_template(processor, config, EXTRACTION_PROMPT, num_images=1)
            res = generate(
                model,
                processor,
                prompt,
                [str(prep_img)],
                max_tokens=384,
                repetition_penalty=1.1,
                temperature=0.0,
                verbose=False,
            )
            raw_text = res.text if hasattr(res, "text") else str(res)
    finally:
        # Xóa file ảnh tạm
        if prep_img.exists() and prep_img != image_path:
            try:
                prep_img.unlink()
            except Exception:
                pass

    latency = round(time.time() - start_time, 2)
    parsed = parse_model_json(raw_text)

    raw_brand = str(parsed.get("brand_name") or "").strip()
    raw_outlet = str(parsed.get("outlet_name") or "").strip()
    raw_bill_number = str(parsed.get("bill_number") or "").strip()
    bill_datetime = str(parsed.get("bill_datetime") or "").strip()
    bill_total = to_int_amount(parsed.get("bill_total"))
    is_valid_bill = bool(parsed.get("is_valid_bill", True))

    optimized_bill_number = optimize_bill_number(raw_bill_number, bill_datetime)

    out_num, out_name, match_score, top_candidates = resolve_outlet(raw_outlet, raw_brand, return_candidates=True, top_n=3)

    return {
        "raw_brand": raw_brand,
        "raw_outlet": raw_outlet,
        "bill_number": optimized_bill_number,
        "raw_bill_number": raw_bill_number,
        "bill_datetime": bill_datetime,
        "bill_total": bill_total,
        "is_valid_bill": is_valid_bill,
        "outlet_number": out_num,
        "resolved_outlet": out_name,
        "match_score": match_score,
        "top_candidates": top_candidates,
        "latency": latency,
        "raw_output": raw_text,
    }
