import streamlit as st
import anthropic
import json
import re
import io
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

st.set_page_config(
    page_title="🧪 Test Case Generator",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
    border: 1px solid #e9ecef;
}
.metric-val { font-size: 32px; font-weight: 700; margin: 0; }
.metric-lbl { font-size: 13px; color: #6c757d; margin: 0; }
.tc-positive { border-left: 4px solid #28a745 !important; }
.tc-negative { border-left: 4px solid #dc3545 !important; }
.tc-boundary { border-left: 4px solid #fd7e14 !important; }
</style>
""", unsafe_allow_html=True)

# ── API KEY ───────────────────────────────────────────────────────────────────
api_key = st.secrets.get("ANTHROPIC_API_KEY", "") if hasattr(st, "secrets") else ""
if not api_key:
    api_key = st.sidebar.text_input(
        "🔑 Anthropic API Key",
        type="password",
        placeholder="sk-ant-...",
        help="Получить бесплатно: https://console.anthropic.com",
    )
if not api_key:
    st.sidebar.warning("Введи API Key для работы")
    st.title("🧪 Test Case Generator из ТЗ")
    st.info("👈 Введи Anthropic API Key в боковой панели чтобы начать")
    st.stop()

client = anthropic.Anthropic(api_key=api_key)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧪 Test Case Generator")
    st.caption("AI-генерация тест-кейсов из ТЗ")
    st.divider()

    st.subheader("⚙️ Настройки генерации")
    n_cases = st.slider("Количество тест-кейсов", 5, 30, 12, 1)

    st.markdown("**Типы сценариев**")
    col_a, col_b, col_c = st.columns(3)
    with col_a: inc_pos = st.checkbox("✅ Positive", value=True)
    with col_b: inc_neg = st.checkbox("❌ Negative", value=True)
    with col_c: inc_bnd = st.checkbox("⚠️ Boundary", value=True)

    st.markdown("**Приоритеты**")
    col_d, col_e, col_f = st.columns(3)
    with col_d: inc_hi  = st.checkbox("🔴 High",   value=True)
    with col_e: inc_med = st.checkbox("🟡 Medium", value=True)
    with col_f: inc_lo  = st.checkbox("🟢 Low",    value=True)

    lang = st.selectbox("Язык тест-кейсов", ["Русский", "English"])
    st.divider()
    st.caption("Powered by Claude · Anthropic")

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
types_needed = []
if inc_pos: types_needed.append("positive")
if inc_neg: types_needed.append("negative")
if inc_bnd: types_needed.append("boundary")
types_str = " | ".join(f'"{t}"' for t in types_needed) or '"positive"'

prios_needed = []
if inc_hi:  prios_needed.append("high")
if inc_med: prios_needed.append("medium")
if inc_lo:  prios_needed.append("low")

SYSTEM = f"""You are a senior QA engineer. Given a requirements document, generate exactly {n_cases} test cases as a JSON array.

Return ONLY the JSON array, no markdown fences, no explanation.

Schema of each item:
{{
  "id": "TC-001",
  "title": "Short descriptive title",
  "type": {types_str},
  "priority": "high" | "medium" | "low",
  "preconditions": "Single string describing preconditions",
  "steps": ["Step 1 description", "Step 2 description"],
  "expected_result": "Single string describing expected result",
  "tags": ["tag1", "tag2"]
}}

IMPORTANT:
- "preconditions" and "expected_result" MUST be plain strings, never arrays
- Cover all requested scenario types proportionally
- Write test cases in {"Russian" if lang == "Русский" else "English"}
- Be specific and actionable in steps
"""

# ── HELPERS ───────────────────────────────────────────────────────────────────
def to_str(v):
    if isinstance(v, list): return ", ".join(str(x) for x in v)
    return str(v) if v is not None else ""

def generate_test_cases(tz_text: str) -> list[dict]:
    if len(tz_text) > 8000:
        tz_text = tz_text[:8000] + "\n...[truncated]"
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Requirements:\n\n{tz_text}"}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except: pass
    try: return json.loads(raw)
    except Exception as e:
        st.error(f"Ошибка парсинга JSON: {e}")
        with st.expander("Сырой ответ модели"): st.code(raw[:2000])
        return []

def to_excel(tcs: list[dict]) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Test Cases"
    headers = ["ID","Title","Type","Priority","Preconditions","Steps","Expected Result","Tags"]
    hf = PatternFill("solid", fgColor="1F4E79")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = hf
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.alignment = Alignment(horizontal="center", vertical="center")
    colors = {"positive":"E8F5E9","negative":"FFEBEE","boundary":"FFF8E1"}
    for row, tc in enumerate(tcs, 2):
        fill = PatternFill("solid", fgColor=colors.get(tc.get("type",""),"FFFFFF"))
        steps_raw = tc.get("steps", [])
        if isinstance(steps_raw, str): steps_raw = [steps_raw]
        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps_raw))
        vals = [to_str(tc.get("id")), to_str(tc.get("title")), to_str(tc.get("type")),
                to_str(tc.get("priority")), to_str(tc.get("preconditions")),
                steps_text, to_str(tc.get("expected_result")),
                ", ".join(str(t) for t in (tc.get("tags") or []))]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.fill = fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col, w in zip(range(1,9), [10,35,12,10,30,50,35,20]):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    ws2 = wb.create_sheet("Stats")
    for r, (lbl, val) in enumerate([
        ("Total",    len(tcs)),
        ("Positive", sum(1 for t in tcs if t.get("type")=="positive")),
        ("Negative", sum(1 for t in tcs if t.get("type")=="negative")),
        ("Boundary", sum(1 for t in tcs if t.get("type")=="boundary")),
        ("",""),
        ("High",   sum(1 for t in tcs if t.get("priority")=="high")),
        ("Medium", sum(1 for t in tcs if t.get("priority")=="medium")),
        ("Low",    sum(1 for t in tcs if t.get("priority")=="low")),
    ], 1):
        ws2.cell(row=r, column=1, value=lbl).font = Font(bold=True)
        ws2.cell(row=r, column=2, value=val)
    ws2.column_dimensions["A"].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

# ── MAIN ──────────────────────────────────────────────────────────────────────
st.title("🧪 Test Case Generator из ТЗ")
st.markdown("Загрузи техническое задание — AI сгенерирует тест-кейсы с экспортом в Excel и JSON")

# Input tabs
tab1, tab2 = st.tabs(["✏️ Текст", "📁 Файл (PDF / DOCX)"])
tz_text = ""

with tab1:
    inp = st.text_area(
        "Вставьте текст технического задания:",
        height=280,
        placeholder="Пример:\n\nFR-01. Авторизация\n- Пользователь вводит логин и пароль\n- При 3 неверных попытках — блокировка 15 минут\n- Пароль минимум 8 символов...",
    )
    if inp:
        tz_text = inp
        chars = len(tz_text)
        color = "normal" if chars < 6000 else "inverse"
        st.caption(f"{chars:,} / 8,000 символов")

with tab2:
    uploaded = st.file_uploader("PDF или DOCX файл", type=["pdf","docx","doc"])
    if uploaded:
        import tempfile
        from pathlib import Path
        suf = Path(uploaded.name).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suf) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        try:
            if suf == ".pdf":
                import fitz
                doc = fitz.open(tmp_path)
                tz_text = "\n\n".join(p.get_text() for p in doc)
                doc.close()
            elif suf in (".docx", ".doc"):
                from docx import Document
                doc = Document(tmp_path)
                tz_text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            st.success(f"✅ Загружено: **{uploaded.name}** — {len(tz_text):,} символов")
            with st.expander("Просмотр текста"):
                st.text(tz_text[:3000] + ("..." if len(tz_text) > 3000 else ""))
        except Exception as e:
            st.error(f"Ошибка чтения файла: {e}")

# Generate button
st.divider()
gen_disabled = not bool(tz_text) or not bool(types_needed)
if st.button("🚀 Генерировать тест-кейсы", type="primary",
             use_container_width=True, disabled=gen_disabled):
    if not types_needed:
        st.error("Выбери хотя бы один тип сценария в настройках")
    else:
        with st.spinner(f"Генерируем {n_cases} тест-кейсов..."):
            tcs = generate_test_cases(tz_text)
            if tcs:
                st.session_state["tcs"] = tcs
                st.session_state["tz"] = tz_text
                st.success(f"✅ Сгенерировано {len(tcs)} тест-кейсов")
            else:
                st.error("Не удалось сгенерировать тест-кейсы. Проверь API ключ и попробуй снова.")

# Results
if "tcs" in st.session_state and st.session_state["tcs"]:
    all_tcs = st.session_state["tcs"]

    active_types = [t for t, on in [("positive",inc_pos),("negative",inc_neg),("boundary",inc_bnd)] if on]
    active_prios = [p for p, on in [("high",inc_hi),("medium",inc_med),("low",inc_lo)] if on]
    tcs = [tc for tc in all_tcs if tc.get("type") in active_types and tc.get("priority") in active_prios]

    st.divider()

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card"><p class="metric-val">{len(all_tcs)}</p><p class="metric-lbl">Всего</p></div>', unsafe_allow_html=True)
    with c2:
        n_pos = sum(1 for t in all_tcs if t.get("type")=="positive")
        st.markdown(f'<div class="metric-card"><p class="metric-val" style="color:#28a745">{n_pos}</p><p class="metric-lbl">✅ Positive</p></div>', unsafe_allow_html=True)
    with c3:
        n_neg = sum(1 for t in all_tcs if t.get("type")=="negative")
        st.markdown(f'<div class="metric-card"><p class="metric-val" style="color:#dc3545">{n_neg}</p><p class="metric-lbl">❌ Negative</p></div>', unsafe_allow_html=True)
    with c4:
        n_bnd = sum(1 for t in all_tcs if t.get("type")=="boundary")
        st.markdown(f'<div class="metric-card"><p class="metric-val" style="color:#fd7e14">{n_bnd}</p><p class="metric-lbl">⚠️ Boundary</p></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Export
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 Скачать Excel (Zephyr / Jira)",
            to_excel(tcs),
            "test_cases.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "📥 Скачать JSON (Zephyr API)",
            json.dumps(tcs, ensure_ascii=False, indent=2),
            "test_cases.json",
            "application/json",
            use_container_width=True,
        )

    # Test case list
    st.subheader(f"📋 Тест-кейсы ({len(tcs)} из {len(all_tcs)})")

    type_icon = {"positive":"✅","negative":"❌","boundary":"⚠️"}
    prio_icon = {"high":"🔴","medium":"🟡","low":"🟢"}

    for tc in tcs:
        label = (
            f"{type_icon.get(tc.get('type',''),'?')} "
            f"**{tc.get('id','?')}** — {tc.get('title','?')}  "
            f"{prio_icon.get(tc.get('priority','medium'),'⚪')}"
        )
        with st.expander(label, expanded=False):
            left, right = st.columns([1, 2])
            with left:
                st.markdown(f"**Тип:** `{tc.get('type','—')}`")
                st.markdown(f"**Приоритет:** `{tc.get('priority','—')}`")
                st.markdown(f"**Предусловия:**  \n{to_str(tc.get('preconditions','—'))}")
                tags = tc.get("tags", [])
                if tags:
                    st.markdown("**Теги:** " + " ".join(f"`{t}`" for t in tags))
            with right:
                st.markdown("**Шаги:**")
                steps = tc.get("steps", [])
                if isinstance(steps, str): steps = [steps]
                for idx, step in enumerate(steps, 1):
                    st.markdown(f"{idx}. {step}")
                st.success(f"**Ожидаемый результат:**  \n{to_str(tc.get('expected_result','—'))}")

elif tz_text and not gen_disabled:
    st.info("👆 Нажми «Генерировать тест-кейсы»")
elif not tz_text:
    st.info("👆 Введи текст ТЗ или загрузи файл")
