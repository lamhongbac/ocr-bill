import os
import time
import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
from PIL import Image

os.environ["HF_HOME"] = "/mnt/data/ocr-bill/cache/huggingface"
model_id = os.getenv("OCR_MODEL_ID", "Qwen/Qwen2-VL-2B-Instruct")

print(f"[*] Đang nạp mô hình {model_id} lên RTX 3060 GPU...")
t0 = time.time()
model = Qwen2VLForConditionalGeneration.from_pretrained(
    model_id,
    torch_dtype=torch.float16,
    device_map="auto"
)
processor = AutoProcessor.from_pretrained(model_id)
print(f"[+] Nạp thành công mô hình trong {time.time() - t0:.2f}s!")
print(f"[*] VRAM đang dùng: {round(torch.cuda.memory_allocated() / (1024**3), 2)} GB / 12 GB")

img_path = "/tmp/test_bill.png"
if os.path.exists(img_path):
    print(f"[*] Bắt đầu suy luận hóa đơn test: {img_path}...")
    t1 = time.time()
    prompt = """Bạn là chuyên gia bóc tách hóa đơn tại Trung tâm Thương mại Gigamall. Hãy đọc ảnh và chỉ trả về MỘT đối tượng JSON:
{"brand_name":"","outlet_name":"","bill_number":"","bill_datetime":"YYYY-MM-DD HH:mm:ss","bill_total":0,"is_valid_bill":true}"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": img_path},
                {"type": "text", "text": prompt},
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
    print(f"[+] KẾT QUẢ SUY LUẬN (Thời gian: {round(time.time() - t1, 2)}s):")
    print(output_texts[0].strip())
