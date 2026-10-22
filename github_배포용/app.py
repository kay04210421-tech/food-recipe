import base64
import json
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import streamlit as st

import agent
import core

st.set_page_config(page_title="냉장고 식단 에이전트", page_icon="🧊", layout="wide")

st.markdown("""
<style>
/* 닫힌 냉장고: 첨부 그림 자체가 클릭 버튼 */
.st-key-fridge{max-width:260px; margin:0 auto;}
.st-key-fridge button{
  width:260px; height:407px; min-height:407px; padding:0; border:none; border-radius:0;
  background:url(data:image/png;base64,__IMG__) center/100% 100% no-repeat transparent;
  color:transparent; font-size:0; box-shadow:none; cursor:pointer; transition:transform .15s, filter .15s;
}
.st-key-fridge [data-testid="stButton"]{width:260px;}
.st-key-fridge button p{display:none;}
.st-key-fridge button:hover{transform:scale(1.03); filter:drop-shadow(0 8px 14px rgba(60,90,120,.35));}
.st-key-fridge button:focus,.st-key-fridge button:active{background-color:transparent; color:transparent; box-shadow:none; border:none;}
/* 열린 냉장고: 문 두 짝이 열리며 안쪽이 보임 */
.fr-scene{position:relative; width:230px; margin-right:30px !important; aspect-ratio:351/549; margin:0 auto; perspective:900px;}
.fr-inside{position:absolute; inset:2% 3%; border-radius:8px; background:linear-gradient(#fdfefe,#e3eef6);
  border:3px solid #7d93a6; box-shadow:inset 0 0 18px rgba(0,0,0,.18); display:flex; flex-direction:column; justify-content:space-around;}
.fr-inside .shelf{border-bottom:5px solid #b9cbd9; font-size:1.7rem; text-align:center; padding-bottom:2px; letter-spacing:4px;}
.fr-door{position:absolute; left:0; width:100%; background:url(data:image/png;base64,__IMG__);
  transform-origin:right center; backface-visibility:visible; animation:frOpen .9s ease-out forwards;}
.fr-top{top:0; height:39.5%; background-size:100% 253%; background-position:top;}
.fr-bot{top:40.5%; height:59.5%; background-size:100% 168%; background-position:bottom; animation-delay:.12s;}
@keyframes frOpen{from{transform:rotateY(0)} to{transform:rotateY(82deg)}}
.cand{border:1px solid #d6dee6; border-radius:14px; padding:12px 14px; margin-bottom:8px;}
</style>
""".replace("__IMG__", base64.b64encode((Path(__file__).parent / "assets" / "fridge.png").read_bytes()).decode()),
    unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("door_open", False)
ss.setdefault("msgs", [])
ss.setdefault("chat_id", uuid.uuid4().hex)

HIST_FILE = Path(__file__).parent / "history" / "chats.json"


def load_chats():
    """저장된 대화 목록(최신순). 파일이 없거나 깨졌으면 빈 목록."""
    try:
        return sorted(json.loads(HIST_FILE.read_text(encoding="utf-8")), key=lambda c: c["ts"], reverse=True)
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _write_chats(chats):
    HIST_FILE.parent.mkdir(exist_ok=True)
    HIST_FILE.write_text(json.dumps(chats, ensure_ascii=False, indent=1), encoding="utf-8")


def save_chat():
    """현재 대화를 기록 파일에 저장(같은 chat_id면 덮어쓰기)."""
    if not ss.msgs:
        return
    first = next((m["content"] for m in ss.msgs if m["role"] == "user"), "대화")
    entry = {"id": ss.chat_id, "title": first, "ts": datetime.now().strftime("%Y-%m-%d %H:%M"), "msgs": ss.msgs}
    _write_chats([entry] + [c for c in load_chats() if c["id"] != ss.chat_id])


def open_chat(cid):
    c = next((c for c in load_chats() if c["id"] == cid), None)
    if c:
        ss.chat_id, ss.msgs, ss.trigger, ss.pending = c["id"], c["msgs"], False, None


def delete_chat(cid):
    """cid가 None이면 전체 삭제."""
    _write_chats([] if cid is None else [c for c in load_chats() if c["id"] != cid])
    if cid is None or cid == ss.chat_id:
        ss.msgs, ss.trigger, ss.pending, ss.chat_id = [], False, None, uuid.uuid4().hex
ss.setdefault("up_n", 0)
ss.setdefault("trigger", False)
ss.setdefault("pending", None)

# ---------------------------------------------------------------- 사이드바
with st.sidebar:
    st.header("설정")
    timeout = st.number_input("응답 제한 시간(초)", min_value=0.01, value=60.0, step=1.0)
    mock = st.selectbox("모의 시험", ["없음", "도구 실패 주입", "호출 상한 1회"],
                        help="실제 응답과 구분되도록 기록에 '모의 시험'으로 표시됩니다.")
    st.caption(f"모델: {agent.os.getenv('OPENAI_MODEL', '(기본)')}")
    if st.button("🗑 새 대화", use_container_width=True):
        ss.msgs, ss.trigger, ss.pending, ss.chat_id = [], False, None, uuid.uuid4().hex
        st.rerun()
    st.divider()
    st.subheader("🕘 질문 기록")
    chats = load_chats()
    if not chats:
        st.caption("아직 저장된 대화가 없습니다. 질문하면 여기에 쌓입니다.")
    for c in chats[:30]:
        a, b = st.columns([5, 1])
        a.button(f"{c['title'][:18]}", key=f"h_{c['id']}", use_container_width=True,
                 help=f"{c['ts']} · 질문 {sum(m['role'] == 'user' for m in c['msgs'])}개",
                 type="primary" if c["id"] == ss.chat_id else "secondary",
                 on_click=open_chat, args=(c["id"],))
        b.button("✕", key=f"d_{c['id']}", help="이 대화 삭제", on_click=delete_chat, args=(c["id"],))
    if chats:
        st.button("기록 전체 삭제", on_click=delete_chat, args=(None,), use_container_width=True)
    st.caption("기록은 history/chats.json에 저장됩니다.")
    st.divider()
    st.caption("추천·계산은 조회일 뿐 재고를 바꾸지 않습니다. 재료 제외는 선호 반영이며 알레르기 안전을 보장하지 않습니다.")


def send(text):
    ss.pending = text


def recipe_link(menu):
    """만개의레시피 검색 링크 (사이트 본문은 복사하지 않고 링크만 제공)."""
    return f"[🔗 만개의레시피에서 '{menu}' 보기](https://www.10000recipe.com/recipe/list.html?q={quote(menu)})"


# ---------------------------------------------------------------- 냉장고 + 업로드
st.title("🧊 냉장고 식단 에이전트")
left, right = st.columns([1, 2.4], gap="large")

with left:
    if ss.door_open:
        st.markdown("""<div class="fr-scene">
          <div class="fr-inside"><div class="shelf">🥚🥕🧅</div><div class="shelf">🍚🥬🧈</div>
          <div class="shelf">🥔🧂🫘</div><div class="shelf">🍶💧🥫</div></div>
          <div class="fr-door fr-top"></div><div class="fr-door fr-bot"></div></div>""", unsafe_allow_html=True)
        if st.button("🚪 문 닫기", use_container_width=True):
            ss.door_open = False
            st.rerun()
    else:
        with st.container(key="fridge"):
            if st.button("냉장고 열기", key="fridge_btn", help="클릭하면 문이 열립니다"):
                ss.door_open = True
                st.rerun()
        st.markdown("<p style='text-align:center;color:#5b7a93'>👆 냉장고를 클릭해서 문을 열어보세요</p>",
                    unsafe_allow_html=True)

up_fridge = up_recipe = None
if ss.door_open:
    with right:
        st.subheader("📥 보유 재료 업로드")
        c1, c2 = st.columns(2)
        up_fridge = c1.file_uploader("냉장고 CSV (재료ID,이름,수량,단위)", type="csv", key=f"uf{ss.up_n}")
        up_recipe = c2.file_uploader("레시피 JSON (선택)", type="json", key=f"ur{ss.up_n}")
        if up_fridge or up_recipe:
            if st.button("기본 파일(data 폴더)로 되돌리기"):
                ss.up_n += 1
                st.rerun()
        else:
            st.caption("업로드하지 않으면 data 폴더의 냉장고.csv · 레시피.json을 사용합니다.")

store = core.Store(up_fridge.getvalue() if up_fridge else None, up_recipe.getvalue() if up_recipe else None)

with right:
    if not store.ok:
        st.error("파일 오류로 메뉴 판단과 계산을 멈췄습니다. 정상 파일로 바꾸면 다시 사용할 수 있습니다.")
        for m in store.errors:
            st.write("• " + m)
    elif ss.door_open:
        t1, t2 = st.tabs([f"보유 재료 {len(store.fridge)}종", f"등록 메뉴 {len(store.recipes)}개"])
        with t1:
            st.table([{"재료": i["이름"], "보유량": i["수량"], "단위": i["단위"]} for i in store.fridge])
        with t2:
            for r in store.recipes:
                with st.expander(f"{r['이름']} (기준 {r['기준인원']}명)"):
                    st.table([{"재료": i["이름"], "분량": i["수량"], "단위": i["단위"],
                               "비고": "" if store.stock(i) else "미등록, 보유 0으로 비교"} for i in r["재료"]])
    else:
        st.info("왼쪽 냉장고 그림을 클릭하면 재료 업로드 칸이 열립니다.")

    # ----------------------------------------------------------- 바로 추천
    if store.ok:
        st.subheader("🍳 이 재료로 만들 수 있는 메뉴")
        a, b, c = st.columns([1, 2, 1.3])
        n = a.number_input("인원", 1, 20, 2)
        ex = b.multiselect("뺄 재료", sorted({i["이름"] for r in store.recipes for i in r["재료"]}))
        only = c.checkbox("있는 재료만", value=False)
        res = core.search_recipes(store, n, ex, only)
        if not res["후보"]:
            st.warning(res.get("안내", "후보가 없습니다."))
        for cd in res["후보"]:
            with st.container(border=True):
                x, y = st.columns([4, 1])
                lack = ", ".join(f"{s['재료']} {s['수량']}{s['단위']}" for s in cd["부족"])
                x.markdown(f"**{cd['메뉴']}** · {cd['인원']}명 · "
                           f"{'✅ 가능' if cd['판정'] == '가능' else '⚠️ ' + cd['판정']}"
                           + (f" (부족: {lack})" if lack else ""))
                x.caption(" · ".join(cd["재료"]))
                x.markdown(recipe_link(cd["메뉴"]))
                y.button("이걸로 할게", key=f"r_{cd['레시피ID']}_{n}",
                         on_click=send, args=(f"{cd['메뉴']}(으)로 할게. {n}명 분량으로 알려줘",))

st.divider()
st.subheader("💬 냉장고에게 물어보기")
st.info("🥇 **재료나 만들고 싶은 메뉴를 말하면 '만개의레시피' 사이트의 추천순 1위 레시피 정보(재료·분량·원문 링크)도 알려드려요.** "
        "냉장고 파일 업로드 없이도 됩니다. 예: \"감자랑 양파로 만들 레시피 알려줘\", \"만개의레시피에서 김치찌개 알려줘\"")
st.caption("예: 냉장고에 쌀 얼마나 있어? · 두 명이 먹을 건데 어떤 메뉴가 나아? 달걀은 빼줘 · 세 명으로 바꿔줘")


# ---------------------------------------------------------------- 결과 렌더링
def _all_calcs():
    return [(i, j) for i, m in enumerate(ss.msgs) for j, r in enumerate(m.get("results", []))
            if r["도구"] == "calculate_recipe"]


def render_calc(res, tag):
    st.markdown(f"**{tag} · {res['메뉴']} {res['인원']}명 기준** (기준 {res['기준인원']}명) · "
                + recipe_link(res["메뉴"]))
    st.table([{"재료": r["재료"], "필요": f"{r['필요']}{r['단위']}", "보유": f"{r['보유']}{r['단위']}"
               if isinstance(r["보유"], (int, float)) else r["보유"],
               "부족": "보류" if r["부족"] is None else f"{r['부족']}{r['단위']}", "비고": r.get("비고", "")}
              for r in res["표"]])
    if res["계산보류"]:
        st.warning(f"계산 보류: {', '.join(res['계산보류'])} (단위 불일치). 장보기를 확정할 수 없습니다.")
    if res["장보기"]:
        st.markdown("🛒 **장보기** " + " · ".join(f"{s['재료']} {s['수량']}{s['단위']}" for s in res["장보기"]))
    elif not res["계산보류"]:
        st.success("추가로 필요한 재료가 없습니다")
    st.caption(res["재고변경"])


def render_message(i, m):
    if m["role"] == "user":
        st.write(m["content"])
        return
    if m.get("error"):
        e = m["error"]
        st.error(f"[{e['kind']}] {e['message']}" + ("  *(시험용 실패)*" if m.get("test") else ""))
        if i == len(ss.msgs) - 1:
            def retry():
                ss.msgs.pop()
                ss.trigger = True
            st.button("🔁 다시 시도", key=f"retry{i}", on_click=retry)
    if m["content"]:
        st.write(m["content"])
    if any(l["상태"] == "실패" for l in m.get("log", [])) and not m.get("error"):
        st.warning("[도구 실패] 일부 도구 호출이 실패했습니다. 실패한 호출은 결과로 쓰지 않았습니다.")
    calcs = _all_calcs()
    for j, r in enumerate(m.get("results", [])):
        if r["도구"] == "search_recipes":
            cond = r["결과"]["조건"]
            st.caption(f"검색 조건: {cond['인원']}명 · 제외 {', '.join(cond['제외재료']) or '없음'}"
                       f"{' · 있는 재료만' if cond['있는재료만'] else ''}")
            for cd in r["결과"]["후보"]:
                with st.container(border=True):
                    x, y = st.columns([4, 1])
                    lack = ", ".join(f"{s['재료']} {s['수량']}{s['단위']}" for s in cd["부족"])
                    x.markdown(f"**{cd['메뉴']}** · {cd['인원']}명 · {cd['판정']}" + (f" (부족: {lack})" if lack else ""))
                    x.caption(" · ".join(cd["재료"]))
                    x.markdown(recipe_link(cd["메뉴"]))
                    y.button("선택", key=f"pick{i}{j}{cd['레시피ID']}", on_click=send,
                             args=(f"{cd['메뉴']}(으)로 할게. {cd['인원']}명 분량으로 알려줘",))
        elif r["도구"] == "calculate_recipe":
            latest = bool(calcs) and calcs[-1] == (i, j)
            render_calc(r["결과"], "✅ 최신 결과" if latest else "🕘 이전 결과")
        elif r["도구"] == "search_web_recipe":
            w = r["결과"]
            with st.container(border=True):
                st.markdown(f"**🥇 만개의레시피 추천순 1위** · [{w['제목']}]({w['링크']})")
                st.caption(f"검색어 '{w['검색어']}' · {w['정보']}")
                st.write(" · ".join(f"{x['재료']} {x['분량']}".strip() for x in w["재료"]) or "재료 정보를 읽지 못했습니다.")
                st.caption("출처: 만개의레시피 — 조리 과정은 링크에서 확인하세요.")
        elif r["도구"] == "get_recipe_steps":
            st.markdown(f"**{r['결과']['메뉴']} 조리 순서** (레시피 원문)")
            for k, s in enumerate(r["결과"]["조리순서"], 1):
                st.write(f"{k}. {s}")
    if m.get("log"):
        with st.expander(f"도구 실행 기록 ({len(m['log'])}건)" + (" · 모의 시험" if m.get("mock") else "")):
            for l in m["log"]:
                st.write(f"`{l['도구']}` {l['인자']} → **{l['상태']}** · {l['요약']}")


for i, m in enumerate(ss.msgs):
    with st.chat_message(m["role"]):
        render_message(i, m)

# ---------------------------------------------------------------- 입력 처리
can_chat = store.ok and agent.api_key_ready()
if not agent.api_key_ready():
    st.warning("OPENAI_API_KEY가 설정되지 않았습니다. data/.env (또는 프로젝트 .env)에 키를 넣고 앱을 다시 시작해 주세요.")
if not store.ok:
    st.caption("파일 오류가 있어 질문을 받을 수 없습니다.")

typed = st.chat_input("냉장고에게 질문하세요 (재료·메뉴를 말하면 만개의레시피 정보도 알려줘요)", disabled=not can_chat)
text = typed or ss.pending
ss.pending = None
if text and can_chat:
    ss.msgs.append({"role": "user", "content": text})
    save_chat()
    ss.trigger = True

if ss.trigger and can_chat:
    ss.trigger = False
    ctx = {}
    for m in ss.msgs:
        for r in m.get("results", []):
            if r["도구"] == "calculate_recipe":
                ctx["선택메뉴"] = {"레시피ID": r["결과"]["레시피ID"], "이름": r["결과"]["메뉴"]}
                ctx["인원"] = r["결과"]["인원"]
            elif r["도구"] == "search_recipes":
                ctx["마지막검색조건"] = r["결과"]["조건"]
    hist = [{"role": m["role"], "content": m["content"]} for m in ss.msgs
            if m["content"] and not m.get("error")]
    is_mock = mock != "없음" or timeout < 1
    with st.chat_message("assistant"), st.spinner("생각하는 중..."):
        out = agent.run_agent(store, hist, ctx, timeout=timeout,
                              max_calls=1 if mock == "호출 상한 1회" else agent.MAX_CALLS,
                              inject_tool_fail=(mock == "도구 실패 주입"))
    ss.msgs.append({"role": "assistant", "content": out["text"], "log": out["log"],
                    "results": out["results"], "error": out["error"], "mock": is_mock,
                    "test": is_mock})
    save_chat()
    st.rerun()

