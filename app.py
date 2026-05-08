import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Segmentation Memory Allocator", layout="wide")

COLORS = [
    "#3B6DAD", "#0F6E56", "#993C1D", "#854F0B",
    "#533FAB", "#3B6D11", "#993556", "#185FA5",
]

# ── Session state bootstrap ────────────────────────────────────────────────────
def init_state():
    defaults = {
        "total_mem": 1024,
        "holes": [],
        "allocated": [],
        "method": "First-Fit",
        "log": [],
        "color_map": {},
        "color_idx": 0,
        "inited": False,
        "init_holes_str": "0,256|512,200",
        "num_segs": 1,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()
S = st.session_state

# ── Core logic ─────────────────────────────────────────────────────────────────
def get_color(proc):
    if proc not in S.color_map:
        S.color_map[proc] = COLORS[S.color_idx % len(COLORS)]
        S.color_idx += 1
    return S.color_map[proc]

def merge_holes(holes):
    h = sorted(holes, key=lambda x: x["base"])
    merged = []
    for x in h:
        if merged and merged[-1]["base"] + merged[-1]["size"] == x["base"]:
            merged[-1]["size"] += x["size"]
        else:
            merged.append(dict(x))
    return merged

def allocate(pname, segs):
    temp_holes = [dict(h) for h in S.holes]
    placed = []
    for s in segs:
        sz = s["size"]
        chosen, ci = None, -1
        if S.method == "First-Fit":
            for i, h in enumerate(temp_holes):
                if h["size"] >= sz:
                    chosen, ci = h, i
                    break
        else:  # Best-Fit
            for i, h in enumerate(temp_holes):
                if h["size"] >= sz and (chosen is None or h["size"] < chosen["size"]):
                    chosen, ci = h, i
        if chosen is None:
            S.log.append(("err", f'Process "{pname}" REJECTED — no hole for segment '
                                  f'"{s["name"]}" (size {sz}). Rolled back.'))
            return False
        placed.append({"process": pname, "segment": s["name"],
                        "base": chosen["base"], "size": sz})
        rem = chosen["size"] - sz
        temp_holes.pop(ci)
        if rem > 0:
            temp_holes.append({"base": chosen["base"] + sz, "size": rem})
        temp_holes.sort(key=lambda x: x["base"])

    S.holes = merge_holes(temp_holes)
    S.allocated.extend(placed)
    names = ", ".join(f'{s["name"]}({s["size"]})' for s in segs)
    S.log.append(("ok", f'Process "{pname}" allocated: {names}'))
    return True

def deallocate(pname):
    segs = [a for a in S.allocated if a["process"] == pname]
    if not segs:
        S.log.append(("err", f'Process "{pname}" not found.'))
        return
    S.allocated = [a for a in S.allocated if a["process"] != pname]
    freed = [{"base": s["base"], "size": s["size"]} for s in segs]
    S.holes = merge_holes(S.holes + freed)
    S.color_map.pop(pname, None)
    S.log.append(("ok", f'Process "{pname}" deallocated. {len(segs)} segment(s) freed.'))

def do_init():
    total = S.total_mem
    holes = []
    for part in S.init_holes_str.split("|"):
        part = part.strip()
        if not part:
            continue
        try:
            b, sz = map(int, part.split(","))
            if sz > 0 and b >= 0 and b + sz <= total:
                holes.append({"base": b, "size": sz})
        except Exception:
            pass
    S.holes = merge_holes(holes)
    S.allocated = []
    S.color_map = {}
    S.color_idx = 0
    S.log = [("info", f"Memory initialized: {total} units. {len(S.holes)} hole(s).")]
    S.inited = True

# ── Memory bar (HTML) ──────────────────────────────────────────────────────────
def render_memory_bar():
    total = S.total_mem
    blocks = sorted(
        [{"type": "alloc", **a} for a in S.allocated] +
        [{"type": "hole",  **h} for h in S.holes],
        key=lambda x: x["base"]
    )
    bar = '<div style="display:flex;height:44px;border-radius:6px;overflow:hidden;border:1px solid #ddd;background:#eee">'
    ptr = 0
    for b in blocks:
        if b["base"] > ptr:
            gap_w = (b["base"] - ptr) / total * 100
            bar += f'<div style="width:{gap_w}%;background:#eee;min-width:2px"></div>'
        w = b["size"] / total * 100
        if b["type"] == "hole":
            bar += (f'<div title="Hole base={b["base"]} size={b["size"]}" '
                    f'style="width:{w}%;min-width:4px;background:#ddd;border:1px dashed #aaa;'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'font-size:10px;color:#999">∅</div>')
        else:
            color = get_color(b["process"])
            label = f'{b["process"]}.{b["segment"]}'
            bar += (f'<div title="{label} [{b["base"]}-{b["base"]+b["size"]-1}]" '
                    f'style="width:{w}%;min-width:4px;background:{color};color:#fff;'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'font-size:10px;font-weight:600;overflow:hidden;white-space:nowrap;padding:0 3px">'
                    f'{"" if w < 4 else label}</div>')
        ptr = b["base"] + b["size"]
    if ptr < total:
        gap_w = (total - ptr) / total * 100
        bar += f'<div style="width:{gap_w}%;background:#eee;min-width:2px"></div>'
    bar += "</div>"
    # address labels
    q = total // 4
    bar += (f'<div style="display:flex;justify-content:space-between;'
            f'font-size:10px;color:#aaa;margin-top:3px">'
            f'<span>0</span><span>{q}</span><span>{q*2}</span>'
            f'<span>{q*3}</span><span>{total}</span></div>')
    return bar

# ── UI ─────────────────────────────────────────────────────────────────────────
st.title("🧠 Segmentation Memory Allocator")

# ── Setup panel ────────────────────────────────────────────────────────────────
with st.expander("⚙️ Setup", expanded=True):
    c1, c2, c3, c4 = st.columns([1.2, 2.5, 1.5, 1])
    with c1:
        S.total_mem = st.number_input("Total memory", min_value=64, max_value=65536,
                                       value=S.total_mem, step=64)
    with c2:
        S.init_holes_str = st.text_input("Initial holes  (base,size | base,size)",
                                          value=S.init_holes_str)
    with c3:
        S.method = st.selectbox("Algorithm", ["First-Fit", "Best-Fit"],
                                  index=0 if S.method == "First-Fit" else 1)
    with c4:
        st.write("")
        st.write("")
        if st.button("Initialize ↺", use_container_width=True):
            do_init()

# ── Memory bar ─────────────────────────────────────────────────────────────────
st.subheader("Memory Layout")
if S.inited:
    st.html(render_memory_bar())
else:
    st.info("Initialize memory to begin.")

st.divider()

# ── Allocate / Deallocate ──────────────────────────────────────────────────────
col_alloc, col_dealloc = st.columns(2)

with col_alloc:
    st.subheader("Allocate Process")
    proc_name = st.text_input("Process name", placeholder="P1", key="proc_name_input")

    st.caption("Segments")
    seg_cols = st.columns([2, 2, 1])
    seg_cols[0].markdown("**Name**")
    seg_cols[1].markdown("**Size**")
    seg_cols[2].markdown("**Del**")

    segs_input = []
    for i in range(S.num_segs):
        c1, c2, c3 = st.columns([2, 2, 1])
        sname = c1.text_input(f"seg_name_{i}", label_visibility="collapsed",
                               placeholder="code", key=f"sn_{i}")
        ssize = c2.number_input(f"seg_size_{i}", label_visibility="collapsed",
                                 min_value=1, value=64, key=f"ss_{i}")
        if i > 0:
            if c3.button("✕", key=f"del_{i}"):
                S.num_segs = max(1, S.num_segs - 1)
                st.rerun()
        if sname:
            segs_input.append({"name": sname, "size": ssize})

    if st.button("+ Add segment"):
        S.num_segs += 1
        st.rerun()

    st.write("")
    if st.button("Allocate ↗", use_container_width=True, type="primary"):
        if not S.inited:
            st.error("Initialize memory first.")
        elif not proc_name:
            st.error("Enter a process name.")
        elif not segs_input:
            st.error("Add at least one named segment.")
        else:
            allocate(proc_name, segs_input)
            st.rerun()

with col_dealloc:
    st.subheader("Deallocate Process")
    dealloc_name = st.text_input("Process name to free", placeholder="P1", key="dealloc_input")
    st.caption("Frees all segments and merges adjacent holes.")
    st.write("")
    if st.button("Deallocate ×", use_container_width=True, type="secondary"):
        if not S.inited:
            st.error("Initialize memory first.")
        elif not dealloc_name:
            st.error("Enter a process name.")
        else:
            deallocate(dealloc_name)
            st.rerun()

    st.write("")
    st.subheader("Operation Log")
    if S.log:
        log_html = '<div style="max-height:180px;overflow-y:auto;background:#f9f9f9;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:12px;line-height:1.9">'
        for t, m in S.log[-30:]:
            color = "#2a7a2a" if t == "ok" else "#cc0000" if t == "err" else "#888"
            icon  = "✓" if t == "ok" else "✗" if t == "err" else "›"
            log_html += f'<div style="color:{color}">{icon} {m}</div>'
        log_html += "</div>"
        st.html(log_html)
    else:
        st.caption("No operations yet.")

st.divider()

# ── Tables ─────────────────────────────────────────────────────────────────────
t1, t2 = st.columns(2)

with t1:
    st.subheader("Holes Table")
    if S.holes:
        rows = [{"#": i+1, "Base": h["base"], "Size": h["size"],
                  "End": h["base"]+h["size"]-1}
                for i, h in enumerate(S.holes)]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No holes.")

with t2:
    st.subheader("Allocated Segments")
    if S.allocated:
        rows = [{"Process": a["process"], "Segment": a["segment"],
                  "Base": a["base"], "Size": a["size"],
                  "End": a["base"]+a["size"]-1}
                for a in S.allocated]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("Nothing allocated.")

st.divider()

# ── Per-process segment table ──────────────────────────────────────────────────
st.subheader("Segment Table per Process")
procs = list(dict.fromkeys(a["process"] for a in S.allocated))
if procs:
    for p in procs:
        color = get_color(p)
        segs = [a for a in S.allocated if a["process"] == p]
        pills = "".join(
            f'<span style="background:{color}22;color:{color};padding:2px 8px;'
            f'border-radius:4px;font-size:12px;margin-right:4px">'
            f'{s["segment"]}@{s["base"]}({s["size"]})</span>'
            for s in segs
        )
        st.html(
            f'<div style="background:#f5f5f5;border-radius:8px;padding:8px 12px;'
            f'margin-bottom:6px;display:flex;align-items:center;gap:12px;font-family:monospace">'
            f'<div style="width:12px;height:12px;border-radius:3px;background:{color};flex-shrink:0"></div>'
            f'<b style="min-width:70px;font-size:13px">{p}</b>'
            f'<div style="display:flex;flex-wrap:wrap;gap:4px">{pills}</div>'
            f'</div>'
        )
else:
    st.caption("No active processes.")