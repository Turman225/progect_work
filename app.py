import streamlit as st
import torch, json, re, io, tempfile
from pathlib import Path
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration, BitsAndBytesConfig
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

st.set_page_config(page_title="Test Case Generator", page_icon="🧪", layout="wide")
st.title("🧪 Test Case Generator from Requirements")
st.markdown("**Model:** Qwen2.5-VL-3B-Instruct")

@st.cache_resource(show_spinner="Loading model...")
def load_model():
    MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    proc = AutoProcessor.from_pretrained(MODEL_ID)
    mdl  = Qwen2_5_VLForConditionalGeneration.from_pretrained(
               MODEL_ID, quantization_config=bnb, device_map="auto", dtype=torch.bfloat16)
    mdl.eval()
    return mdl, proc, device

model, processor, device = load_model()
st.success(f"Model ready | {device.upper()}")

SYSTEM = (
    "You are a senior QA engineer. Given requirements, output a JSON array of test cases ONLY.\n"
    'Format: [{"id":"TC-001","title":"...","type":"positive|negative|boundary",'
    '"priority":"high|medium|low","preconditions":"...","steps":["..."],'
    '"expected_result":"...","tags":["..."]}]\n'
    "Minimum 10 test cases. No markdown, no explanation, JSON only."
)

def generate(tz, n=10):
    if len(tz) > 3000: tz = tz[:3000] + "\n...[truncated]"
    msgs = [{"role":"system","content":SYSTEM},
            {"role":"user","content":f"Requirements:\n\n{tz}\n\nGenerate {n} test cases."}]
    text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp  = processor(text=[text], return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=2500, do_sample=True,
                             temperature=0.3, top_p=0.9, repetition_penalty=1.1,
                             pad_token_id=processor.tokenizer.eos_token_id)
    raw = processor.tokenizer.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    raw = re.sub(r"```(?:json)?","",raw).strip().rstrip("`").strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except: pass
    try: return json.loads(raw)
    except: return []

def to_excel(tcs):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title="Test Cases"
    hdrs = ["ID","Title","Type","Priority","Preconditions","Steps","Expected Result","Tags"]
    hf = PatternFill("solid", fgColor="1F4E79"); hfont = Font(bold=True, color="FFFFFF")
    for c, h in enumerate(hdrs,1):
        cell=ws.cell(row=1,column=c,value=h); cell.fill=hf; cell.font=hfont
        cell.alignment=Alignment(horizontal="center")
    colors={"positive":"E8F5E9","negative":"FFEBEE","boundary":"FFF8E1"}
    for r,tc in enumerate(tcs,2):
        fill=PatternFill("solid",fgColor=colors.get(tc.get("type",""),"FFFFFF"))
        vals=[tc.get("id"),tc.get("title"),tc.get("type"),tc.get("priority"),
              tc.get("preconditions"),"\n".join(f"{i+1}. {s}" for i,s in enumerate(tc.get("steps",[]))),
              tc.get("expected_result"),", ".join(tc.get("tags",[]))]
        for c,v in enumerate(vals,1):
            cell=ws.cell(row=r,column=c,value=v); cell.fill=fill
            cell.alignment=Alignment(wrap_text=True,vertical="top")
    for c,w in zip(range(1,9),[10,35,12,10,30,50,35,20]):
        ws.column_dimensions[get_column_letter(c)].width=w
    ws.auto_filter.ref=ws.dimensions; ws.freeze_panes="A2"
    buf=io.BytesIO(); wb.save(buf); buf.seek(0); return buf

# Sidebar
with st.sidebar:
    st.header("Settings")
    n_cases = st.slider("Number of test cases", 5, 20, 10)
    ftype   = st.multiselect("Filter by type",     ["positive","negative","boundary"], default=["positive","negative","boundary"])
    fprio   = st.multiselect("Filter by priority", ["high","medium","low"],            default=["high","medium","low"])

# Input
st.header("Requirements Input")
tab1, tab2 = st.tabs(["Text input", "Upload PDF/DOCX"])
tz_text = ""
with tab1:
    inp = st.text_area("Paste requirements text:", height=300)
    if inp: tz_text = inp
with tab2:
    f = st.file_uploader("Upload PDF or DOCX", type=["pdf","docx","doc"])
    if f:
        suf = Path(f.name).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suf) as tmp:
            tmp.write(f.read()); tp=tmp.name
        if suf==".pdf":
            import fitz
            doc=fitz.open(tp); tz_text="\n\n".join(p.get_text() for p in doc); doc.close()
        elif suf in (".docx",".doc"):
            from docx import Document
            doc=Document(tp); tz_text="\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        st.success(f"Loaded: {f.name} ({len(tz_text)} chars)")
        with st.expander("Preview"): st.text(tz_text[:2000])

if tz_text:
    st.info(f"Requirements: {len(tz_text)} chars")
    if st.button("Generate Test Cases", type="primary", use_container_width=True):
        with st.spinner("Generating..."):
            st.session_state["tcs"] = generate(tz_text, n_cases)

if "tcs" in st.session_state and st.session_state["tcs"]:
    tcs = [tc for tc in st.session_state["tcs"]
           if tc.get("type") in ftype and tc.get("priority") in fprio]

    st.header(f"Test Cases ({len(tcs)})")
    c1,c2,c3,c4 = st.columns(4)
    all_tcs = st.session_state["tcs"]
    c1.metric("Total",    len(all_tcs))
    c2.metric("Positive", sum(1 for t in all_tcs if t.get("type")=="positive"))
    c3.metric("Negative", sum(1 for t in all_tcs if t.get("type")=="negative"))
    c4.metric("Boundary", sum(1 for t in all_tcs if t.get("type")=="boundary"))

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("Download Excel", to_excel(tcs), "test_cases.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    with col2:
        st.download_button("Download JSON", json.dumps(tcs, ensure_ascii=False, indent=2),
                           "test_cases.json", "application/json", use_container_width=True)

    icons_t = {"positive":"OK","negative":"FAIL","boundary":"EDGE"}
    icons_p = {"high":"HIGH","medium":"MED","low":"LOW"}
    for tc in tcs:
        with st.expander(f"[{icons_t.get(tc.get('type',''),'?')}] {tc.get('id','?')} - {tc.get('title','?')} [{icons_p.get(tc.get('priority','medium'),'?')}]"):
            l, r = st.columns([1,2])
            with l:
                st.markdown(f"**Type:** {tc.get('type')}")
                st.markdown(f"**Priority:** {tc.get('priority')}")
                st.markdown(f"**Preconditions:** {tc.get('preconditions')}")
                if tc.get("tags"): st.markdown("**Tags:** " + " ".join(f"`{t}`" for t in tc["tags"]))
            with r:
                st.markdown("**Steps:**")
                for i, s in enumerate(tc.get("steps",[]),1): st.markdown(f"{i}. {s}")
                st.success(f"**Expected:** {tc.get('expected_result')}")
elif tz_text:
    st.info("Press Generate button")
else:
    st.warning("Enter requirements text or upload a file")
