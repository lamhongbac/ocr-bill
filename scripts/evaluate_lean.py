"""
POC Gate 1 - OCR hóa đơn bằng VLM (Qwen2-VL-7B-Instruct-4bit) trên Mac mini (mlx-vlm).
Chạy offline 100%. Đầu vào: test_images/ + master_outlets.json. Đầu ra: results.csv + report.html.

Cách chạy:
    source venv/bin/activate
    python evaluate_lean.py                # chạy toàn bộ ảnh
    python evaluate_lean.py --limit 3      # chạy thử 3 ảnh
"""
import argparse
import base64
import difflib
import html
import json
import os
import re
import time
import unicodedata
from pathlib import Path

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import pandas as pd
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent.parent
MASTER_OUTLETS_FILE = BASE_DIR / "master_outlets.json"
IMAGE_DIR = BASE_DIR / "test_images"
LOCAL_MODEL_DIR = BASE_DIR / "models" / "Qwen2-VL-7B-Instruct-4bit"
HF_MODEL_ID = "mlx-community/Qwen2-VL-7B-Instruct-4bit"
HTML_REPORT_FILE = BASE_DIR / "report.html"
CSV_REPORT_FILE = BASE_DIR / "results.csv"
WORK_DIR = BASE_DIR / ".work"           # ảnh đã xoay/thu nhỏ để đưa vào model

VALID_EXTS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_IMAGE_SIDE = 1600                   # giới hạn cạnh dài để kiểm soát tốc độ / RAM
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


# ----------------------------- Tiện ích -----------------------------

def normalize(text):
    """Bỏ dấu tiếng Việt, ký tự đặc biệt, viết hoa để so khớp mờ."""
    if not text:
        return ""
    text = str(text).replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
    return re.sub(r"\s+", " ", text).strip()


def load_master_outlets():
    if not MASTER_OUTLETS_FILE.exists():
        print("[!] Không tìm thấy master_outlets.json, bỏ qua bước chuẩn hóa tên quán.")
        return []
    with open(MASTER_OUTLETS_FILE, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    print(f"[+] Đã nạp {len(data)} cửa hàng từ {MASTER_OUTLETS_FILE.name}")
    return data


def build_outlet_index(master_outlets):
    """Mỗi outlet có nhiều 'khóa' để so khớp: outlet_name, outlet_number, brand_name."""
    index = []
    for o in master_outlets:
        keys = {normalize(o.get("outlet_name")), normalize(o.get("outlet_number"))}
        brand = normalize(o.get("brand_name"))
        if brand:
            keys.add(brand)
        index.append((o, {k for k in keys if k}))
    return index


def _score(candidate, key):
    if not candidate or not key:
        return 0.0
    if candidate == key:
        return 1.0
    # Tên ngắn nằm trọn trong chuỗi dài (VD: "HIGHLANDS" trong "HIGHLANDS COFFEE GIGAMALL")
    short, long_ = sorted((candidate, key), key=len)
    if len(short) >= 4 and re.search(rf"\b{re.escape(short)}\b", long_):
        return 0.9
    return difflib.SequenceMatcher(None, candidate, key).ratio()


def resolve_outlet(raw_outlet, raw_brand, outlet_index):
    """Trả về (outlet_number, outlet_name chuẩn CRM, điểm khớp). Không khớp -> (None, None, điểm)."""
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


def parse_model_json(text):
    """Tìm khối JSON trong output của model, có cơ chế dự phòng bằng regex nếu JSON bị cắt cụt."""
    if not text:
        raise ValueError("Model trả về rỗng")
    clean = text.replace("```json", "").replace("```", "").strip()
    start = clean.find("{")
    if start != -1:
        end = clean.rfind("}")
        if end > start:
            try:
                return json.loads(clean[start:end + 1])
            except Exception:
                pass
    # Regex fallback nếu JSON bị lỗi cú pháp hoặc bị cụt
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
    raise ValueError("Không tìm thấy JSON hợp lệ trong output")


def to_int_amount(value):
    """'1.250.000 đ' / '1,250,000' / 1250000.0 -> 1250000"""
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(round(value))
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else 0


def to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "co", "có"}


def prepare_image(img_path):
    """Xoay theo EXIF, chuyển RGB, giới hạn kích thước. Trả về đường dẫn ảnh tạm."""
    WORK_DIR.mkdir(exist_ok=True)
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        out = WORK_DIR / (img_path.stem + ".jpg")
        im.save(out, "JPEG", quality=92)
    return out


def image_to_data_uri(img_path, max_side=900):
    """Nhúng ảnh (thu nhỏ) vào HTML để file report gọn và mở được ở máy khác."""
    try:
        with Image.open(img_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((max_side, max_side))
            from io import BytesIO
            buf = BytesIO()
            im.save(buf, "JPEG", quality=80)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


# ----------------------------- Model -----------------------------

def load_model():
    from mlx_vlm import load
    from mlx_vlm.utils import load_config

    model_ref = str(LOCAL_MODEL_DIR) if (LOCAL_MODEL_DIR / "config.json").exists() else HF_MODEL_ID
    print(f"[*] Nạp mô hình {model_ref} vào Unified Memory...")
    model, processor = load(model_ref)
    config = load_config(model_ref)
    print("[+] Nạp mô hình thành công!\n")
    return model, processor, config


def run_inference(model, processor, config, image_path):
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    prompt = apply_chat_template(processor, config, EXTRACTION_PROMPT, num_images=1)
    result = generate(model, processor, prompt, [str(image_path)],
                      max_tokens=384, repetition_penalty=1.1, temperature=0.0, verbose=False)
    return result.text if hasattr(result, "text") else str(result)


# ----------------------------- Báo cáo HTML -----------------------------

def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def generate_html_report(items, avg_latency):
    cards = []
    for idx, it in enumerate(items, 1):
        if it["status"] == "error":
            body = f'<div class="field err">LỖI: {esc(it["error"])}</div>'
        else:
            total_fmt = f'{it["bill_total"]:,} đ'.replace(",", ".") if it["bill_total"] else "—"
            matched = (f'{esc(it["resolved_outlet"])} <small>({esc(it["outlet_number"])}, {it["match_score"]})</small>'
                       if it["outlet_number"] else f'<span class="nomatch">Chưa khớp ({it["match_score"]})</span>')
            body = f"""
                <div class="field"><span class="label">Thương hiệu AI:</span> <span class="val">{esc(it["raw_brand"])}</span></div>
                <div class="field"><span class="label">Quán AI đọc:</span> <span class="val">{esc(it["raw_outlet"])}</span></div>
                <div class="field"><span class="label">Quán CRM:</span> <span class="val val-outlet">{matched}</span></div>
                <div class="field"><span class="label">Số bill:</span> <span class="val">{esc(it["bill_number"])}</span></div>
                <div class="field"><span class="label">Ngày giờ:</span> <span class="val">{esc(it["bill_datetime"])}</span></div>
                <div class="field"><span class="label">Tổng tiền:</span> <span class="val val-total">{esc(total_fmt)}</span></div>
                <div class="field"><span class="label">Hợp lệ:</span> <span class="val">{"✅ Hợp lệ" if it["is_valid"] else "🚫 Không hợp lệ / rác"}</span></div>"""
        cards.append(f"""
        <article class="card" data-file="{esc(it["filename"])}">
            <div class="img-box" data-full="{it["img_b64"]}"><img src="{it["img_b64"]}" alt="Bill {idx}" loading="lazy"></div>
            <div class="data-box">
                <div class="head"><b>#{idx}</b> {esc(it["filename"])} <span class="lat">{it["latency"]}s</span></div>
                {body}
                <div class="actions">
                    <div class="grp" data-field="total"><span>Tổng tiền</span>
                        <button class="ok" data-v="pass">✅</button><button class="ng" data-v="fail">❌</button></div>
                    <div class="grp" data-field="outlet"><span>Cửa hàng</span>
                        <button class="ok" data-v="pass">✅</button><button class="ng" data-v="fail">❌</button></div>
                    <div class="grp" data-field="valid"><span>Hợp lệ</span>
                        <button class="ok" data-v="pass">✅</button><button class="ng" data-v="fail">❌</button></div>
                </div>
            </div>
        </article>""")

    n_err = sum(1 for i in items if i["status"] == "error")
    page = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Báo cáo nghiệm thu OCR VLM – Gate 1</title>
<style>
:root {{ --bg:#0f1117; --card:#181b24; --line:#2a2f3d; --txt:#e6e8ee; --mut:#8b93a7; --ok:#22c55e; --ng:#ef4444; --acc:#60a5fa; }}
* {{ box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--txt); margin:0; }}
header {{ position:sticky; top:0; z-index:5; background:rgba(15,17,23,.92); backdrop-filter:blur(8px); border-bottom:1px solid var(--line); padding:14px 24px; }}
h1 {{ font-size:18px; margin:0 0 8px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; font-size:13px; }}
.pill {{ background:#222838; border:1px solid var(--line); padding:5px 12px; border-radius:999px; }}
.pill b {{ color:var(--acc); }} .pill.pass b {{ color:var(--ok); }} .pill.fail b {{ color:var(--ng); }}
.tools button {{ background:#2563eb; color:#fff; border:0; padding:7px 14px; border-radius:8px; cursor:pointer; font-weight:600; }}
.tools button.sec {{ background:#374151; }}
main {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(560px,1fr)); gap:16px; padding:20px 24px; }}
.card {{ background:var(--card); border:2px solid var(--line); border-radius:14px; display:flex; overflow:hidden; transition:border-color .2s; }}
.card.all-pass {{ border-color:var(--ok); }} .card.has-fail {{ border-color:var(--ng); }}
.img-box {{ width:230px; min-width:230px; background:#000; display:flex; align-items:center; justify-content:center; cursor:zoom-in; }}
.img-box img {{ max-width:100%; max-height:320px; object-fit:contain; }}
.data-box {{ padding:12px 14px; flex:1; font-size:13px; display:flex; flex-direction:column; gap:5px; }}
.head {{ color:var(--mut); font-size:12px; }} .lat {{ float:right; }}
.label {{ color:var(--mut); display:inline-block; width:105px; }}
.val-total {{ color:#fb923c; font-size:16px; font-weight:700; }} .val-outlet {{ color:var(--acc); font-weight:600; }}
.nomatch {{ color:#f59e0b; }} .err {{ color:var(--ng); }}
.actions {{ margin-top:auto; padding-top:8px; border-top:1px solid var(--line); display:flex; gap:12px; flex-wrap:wrap; }}
.grp {{ display:flex; align-items:center; gap:4px; }} .grp span {{ color:var(--mut); font-size:12px; margin-right:2px; }}
.grp button {{ background:#222838; border:1px solid var(--line); border-radius:6px; padding:3px 8px; cursor:pointer; }}
.grp button.ok.on {{ background:var(--ok); }} .grp button.ng.on {{ background:var(--ng); }}
#lightbox {{ position:fixed; inset:0; background:rgba(0,0,0,.9); display:none; align-items:center; justify-content:center; z-index:10; cursor:zoom-out; }}
#lightbox img {{ max-width:95vw; max-height:95vh; }}
</style></head>
<body>
<header>
  <h1>BÁO CÁO KIỂM THỬ TRỰC QUAN – POC GATE 1 (Qwen2-VL-7B 4bit / Mac mini M4)</h1>
  <div class="stats">
    <span class="pill">Tổng bill: <b>{len(items)}</b></span>
    <span class="pill">Lỗi xử lý: <b>{n_err}</b></span>
    <span class="pill">Latency TB: <b>{avg_latency:.2f}s</b> (≤ 2.2s)</span>
    <span class="pill" id="s-total">Tổng tiền: <b>–</b></span>
    <span class="pill" id="s-outlet">Cửa hàng: <b>–</b></span>
    <span class="pill" id="s-valid">Hợp lệ: <b>–</b></span>
    <span class="pill">Đã chấm: <b id="s-done">0</b>/{len(items)}</span>
    <span class="tools"><button id="btn-export">⬇ Xuất kết quả chấm (CSV)</button> <button class="sec" id="btn-reset">Xóa chấm</button></span>
  </div>
</header>
<main>{"".join(cards)}</main>
<div id="lightbox"><img alt="Ảnh phóng to"></div>
<script>
const KEY = "ocr-gate1-" + {json.dumps(str(int(time.time())))};
const state = JSON.parse(localStorage.getItem(KEY) || "{{}}");
const cards = [...document.querySelectorAll(".card")];
function render() {{
  const agg = {{total:[0,0], outlet:[0,0], valid:[0,0]}}; let done = 0;
  cards.forEach(c => {{
    const s = state[c.dataset.file] || {{}};
    c.querySelectorAll(".grp").forEach(g => {{
      const v = s[g.dataset.field];
      g.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === v));
      if (v) {{ agg[g.dataset.field][1]++; if (v === "pass") agg[g.dataset.field][0]++; }}
    }});
    const vals = Object.values(s);
    c.classList.toggle("has-fail", vals.includes("fail"));
    c.classList.toggle("all-pass", vals.length >= 2 && !vals.includes("fail"));
    if (s.total && s.outlet) done++;
  }});
  const goal = {{total:95, outlet:90, valid:0}};
  for (const k in agg) {{
    const [p, n] = agg[k], el = document.getElementById("s-" + k);
    const pct = n ? (100 * p / n) : null;
    el.querySelector("b").textContent = n ? `${{pct.toFixed(1)}}% (${{p}}/${{n}})` : "–";
    el.classList.toggle("pass", n > 0 && pct >= goal[k]);
    el.classList.toggle("fail", n > 0 && pct < goal[k]);
  }}
  document.getElementById("s-done").textContent = done;
  localStorage.setItem(KEY, JSON.stringify(state));
}}
document.querySelector("main").addEventListener("click", e => {{
  const btn = e.target.closest(".grp button");
  if (btn) {{
    const file = btn.closest(".card").dataset.file, field = btn.closest(".grp").dataset.field;
    state[file] = state[file] || {{}};
    state[file][field] = state[file][field] === btn.dataset.v ? undefined : btn.dataset.v;
    render(); return;
  }}
  const box = e.target.closest(".img-box");
  if (box) {{ const lb = document.getElementById("lightbox"); lb.querySelector("img").src = box.dataset.full; lb.style.display = "flex"; }}
}});
document.getElementById("lightbox").addEventListener("click", e => e.currentTarget.style.display = "none");
document.getElementById("btn-reset").addEventListener("click", () => {{
  if (confirm("Xóa toàn bộ kết quả chấm?")) {{ for (const k in state) delete state[k]; render(); }}
}});
document.getElementById("btn-export").addEventListener("click", () => {{
  const q = v => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  const rows = [["filename","total","outlet","valid"].join(",")];
  cards.forEach(c => {{ const s = state[c.dataset.file] || {{}}; rows.push([q(c.dataset.file), q(s.total), q(s.outlet), q(s.valid)].join(",")); }});
  const blob = new Blob(["\\ufeff" + rows.join("\\n")], {{type:"text/csv"}});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "gate1_audit.csv"; a.click();
}});
render();
</script>
</body></html>"""
    HTML_REPORT_FILE.write_text(page, encoding="utf-8")


# ----------------------------- Main -----------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Chỉ chạy N ảnh đầu (để thử)")
    args = ap.parse_args()

    if not IMAGE_DIR.exists():
        IMAGE_DIR.mkdir()
    image_files = sorted(f for f in IMAGE_DIR.iterdir()
                         if f.suffix.lower() in VALID_EXTS and not f.name.startswith("._"))
    if args.limit:
        image_files = image_files[:args.limit]
    total = len(image_files)
    if total == 0:
        print(f"[!] Thư mục {IMAGE_DIR} chưa có ảnh. Vui lòng copy 50-100 ảnh bill vào đây!")
        return

    outlet_index = build_outlet_index(load_master_outlets())
    model, processor, config = load_model()

    # Warm-up để latency đo được không tính thời gian compile lần đầu
    try:
        run_inference(model, processor, config, prepare_image(image_files[0]))
    except Exception:
        pass

    print(f"[*] Bắt đầu bóc tách {total} ảnh...\n")
    items = []
    for idx, img_path in enumerate(image_files, 1):
        item = {"filename": img_path.name, "status": "ok", "error": "", "latency": 0.0,
                "raw_brand": "", "raw_outlet": "", "outlet_number": None, "resolved_outlet": None,
                "match_score": 0.0, "bill_number": "", "bill_datetime": "", "bill_total": 0,
                "is_valid": False, "raw_output": ""}
        start_t = time.time()
        try:
            work_img = prepare_image(img_path)
            output = run_inference(model, processor, config, work_img)
            item["latency"] = round(time.time() - start_t, 2)
            item["raw_output"] = output.strip()
            pred = parse_model_json(output)

            item["raw_brand"] = str(pred.get("brand_name") or "")
            item["raw_outlet"] = str(pred.get("outlet_name") or "")
            item["bill_number"] = str(pred.get("bill_number") or "")
            item["bill_datetime"] = str(pred.get("bill_datetime") or "")
            item["bill_total"] = to_int_amount(pred.get("bill_total"))
            item["is_valid"] = to_bool(pred.get("is_valid_bill", False))
            num, name, score = resolve_outlet(item["raw_outlet"], item["raw_brand"], outlet_index)
            item.update(outlet_number=num, resolved_outlet=name, match_score=score)
            print(f"[{idx}/{total}] {img_path.name} | {item['latency']}s | Tiền: {item['bill_total']:,} | "
                  f"Quán: {name or 'Chưa khớp'} ({item['raw_outlet']})")
        except Exception as e:
            item["status"] = "error"
            item["error"] = f"{type(e).__name__}: {e}"
            item["latency"] = item["latency"] or round(time.time() - start_t, 2)
            print(f"[{idx}/{total}] {img_path.name} | LỖI: {item['error']}")
        item["img_b64"] = image_to_data_uri(img_path)
        items.append(item)

    df = pd.DataFrame(items).drop(columns=["img_b64"])
    df.to_csv(CSV_REPORT_FILE, index=False, encoding="utf-8-sig")
    ok = df[df["status"] == "ok"]
    avg_lat = ok["latency"].mean() if len(ok) else 0.0
    generate_html_report(items, avg_lat)

    print("\n" + "=" * 60)
    print("          HOÀN THÀNH BÓC TÁCH GATE 1")
    print("=" * 60)
    print(f"1. Xử lý thành công:     {len(ok)}/{total} (lỗi: {total - len(ok)})")
    print(f"2. Latency trung bình:   {avg_lat:.2f} s/bill (mục tiêu ≤ 2.2s)")
    print(f"3. Khớp outlet tự động:  {ok['outlet_number'].notna().sum()}/{len(ok)}")
    print(f"4. Dữ liệu:              {CSV_REPORT_FILE.name}")
    print(f"5. Báo cáo nghiệm thu:   {HTML_REPORT_FILE.name}")
    print("=" * 60)
    print("👉 Mở report.html trên trình duyệt để chấm ĐẠT/SAI.")


if __name__ == "__main__":
    main()
