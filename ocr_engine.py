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
from pathlib import Path
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent
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
- bill_total là số tiền CUỐI CÙNG khách thực trả (Tổng thanh toán / Khách phải trả / Total due) SAU khi đã trừ giảm giá, voucher, điểm. Không lấy tiền giảm giá, không lấy tiền khách đưa, không lấy tiền thối lại. Chỉ ghi số nguyên, không dấu chấm phẩy, không đơn vị.
- is_valid_bill = false nếu ảnh không phải hóa đơn mua hàng, hoặc quá mờ không đọc được tổng tiền.
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


def resolve_outlet(raw_outlet, raw_brand):
    """So khớp mờ trả về (outlet_number, outlet_name, match_score)."""
    outlet_index = get_outlet_index()
    candidates = [c for c in {normalize(raw_outlet), normalize(raw_brand)} if c]
    if not candidates or not outlet_index:
        return None, None, 0.0

    best_obj, best_score = None, 0.0
    for obj, keys in outlet_index:
        for cand in candidates:
            for key in keys:
                s = _score(cand, key)
                if s > best_score:
                    best_obj, best_score = obj, s

    if best_obj and best_score >= MATCH_CUTOFF:
        return best_obj.get("outlet_number"), best_obj.get("outlet_name"), round(best_score, 2)
    return None, None, round(best_score, 2)


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
                model_id = os.getenv("OCR_MODEL_ID", "Qwen/Qwen2-VL-2B-Instruct")
                gpu_name = torch.cuda.get_device_name(0)
                print(f"[*] [OCR Engine] Phát hiện NVIDIA GPU ({gpu_name}). Đang nạp {model_id} qua PyTorch CUDA...")
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
                _processor = AutoProcessor.from_pretrained(model_id)
                _config = _model.config
                _device = "cuda"
                print(f"[+] [OCR Engine] Đã nạp xong mô hình lên NVIDIA GPU trong {time.time() - t0:.2f}s!")
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


def to_int_amount(value):
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(round(value))
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else 0


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
    bill_number = str(parsed.get("bill_number") or "").strip()
    bill_datetime = str(parsed.get("bill_datetime") or "").strip()
    bill_total = to_int_amount(parsed.get("bill_total"))
    is_valid_bill = bool(parsed.get("is_valid_bill", True))

    out_num, out_name, match_score = resolve_outlet(raw_outlet, raw_brand)

    return {
        "raw_brand": raw_brand,
        "raw_outlet": raw_outlet,
        "bill_number": bill_number,
        "bill_datetime": bill_datetime,
        "bill_total": bill_total,
        "is_valid_bill": is_valid_bill,
        "outlet_number": out_num,
        "resolved_outlet": out_name,
        "match_score": match_score,
        "latency": latency,
        "raw_output": raw_text,
    }
