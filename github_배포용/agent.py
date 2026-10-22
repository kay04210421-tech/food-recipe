"""OpenAI tool-calling 에이전트 루프. 도구 선택은 LLM이, 수량 계산은 core.py 코드가 한다."""
import json
import os

from dotenv import load_dotenv

import core
import web

load_dotenv(core.DATA_DIR / ".env")
load_dotenv(core.DATA_DIR.parent / ".env", override=True)

MAX_CALLS = 8

SYSTEM = """너는 '냉장고 식단 에이전트'다. 한국어로 짧고 친절하게 답한다.
- 재고·메뉴·조리순서·수량은 반드시 도구로 조회한다. 추측하거나 직접 계산하지 않는다.
- 질문에 필요한 도구만 호출한다. 재료 조회나 메뉴 목록만 물으면 그 도구만 쓰고, 인원을 묻거나 식단 계산을 덧붙이지 않는다.
- 메뉴 추천 요청에 인원이 없으면 도구를 호출하지 말고 먼저 몇 명인지 묻는다. 제외 재료는 선택 사항이라 길게 캐묻지 않는다.
- '있는 재료만'이면 search_recipes의 only_available=true. 후보가 없으면 없다고 알리고 조건을 바꿀지 묻는다.
- 후속 요청(인원 변경 등)은 아래 '대화 상태'의 메뉴를 유지하고 인원만 바꿔 calculate_recipe를 다시 호출한다.
- 제외 재료가 추가되면 이전 조건과 합쳐 search_recipes를 다시 호출한다. 재료를 임의로 뺀 조리법을 만들지 않는다.
- '그걸/그거'처럼 대상이 없고 대화 상태에도 선택된 메뉴가 없으면 도구 없이 어떤 메뉴인지 묻는다.
- 계산 표는 화면이 도구 반환값으로 따로 보여 준다. 답변에 표의 숫자를 바꿔 쓰지 말고, 핵심(부족한 재료)만 문장으로 요약한다.
- 사용자가 직접 재료나 메뉴를 말하며 레시피를 알려 달라고 하거나 만개의레시피를 언급하면(냉장고 파일 업로드 없이도) search_web_recipe로 추천순 1위를 가져와 답한다.
  제목, 인분·시간·난이도, 재료와 분량을 간단히 안내하고 출처 링크를 붙인다. 조리 과정은 옮겨 쓰지 말고 링크에서 보라고 안내한다. 이 경우 냉장고 재고 계산을 덧붙이지 않는다.
  '내 냉장고 재료로'라고 하면 재고 도구로 재료를 확인한 뒤 그 재료로 검색한다.
- 추천과 계산은 조회일 뿐 재고를 줄이지 않는다. 알레르기 안전은 보장하지 않는다."""


def api_key_ready():
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _context_text(ctx):
    if not ctx:
        return "대화 상태: 아직 선택한 메뉴 없음."
    return "대화 상태: " + json.dumps(ctx, ensure_ascii=False)


def run_agent(store, history, ctx, timeout=60.0, max_calls=MAX_CALLS, inject_tool_fail=False):
    """history: [{role, content}]. 반환: dict(text, log, results, error)

    error: None | {"kind": "모델 실패"|"도구 실패"|"호출 상한", "message": str}
    log는 실제로 실행한 도구 호출만 담는다.
    """
    from openai import BadRequestError, OpenAI

    log, results, calls = [], [], 0
    msgs = [{"role": "system", "content": SYSTEM + "\n" + _context_text(ctx)}] + history
    tools = [{"type": "function", "function": s} for s in core.TOOL_SPECS + [web.TOOL_SPEC]]
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=timeout, max_retries=0)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        extra = {"reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "none")}  # 추론 모델은 도구 호출 시 none 필요
        while True:
            try:
                resp = client.chat.completions.create(model=model, messages=msgs, tools=tools, **extra)
            except BadRequestError as e:
                if not extra or "reasoning_effort" not in str(e):
                    raise
                extra = {}  # 이 모델이 파라미터를 지원하지 않으면 빼고 재시도
                resp = client.chat.completions.create(model=model, messages=msgs, tools=tools)
            m = resp.choices[0].message
            if not m.tool_calls:
                return {"text": m.content or "", "log": log, "results": results, "error": None}
            msgs.append({"role": "assistant", "content": m.content,
                         "tool_calls": [{"id": t.id, "type": "function",
                                         "function": {"name": t.function.name, "arguments": t.function.arguments}}
                                        for t in m.tool_calls]})
            for t in m.tool_calls:
                if calls >= max_calls:
                    return {"text": "", "log": log, "results": results,
                            "error": {"kind": "호출 상한", "message": f"도구 호출이 상한({max_calls}회)에 도달해 중단했습니다."}}
                calls += 1
                try:
                    args = json.loads(t.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if inject_tool_fail:
                    out = {"오류": "시험용 도구 실패"}
                elif t.function.name == web.TOOL_SPEC["name"]:
                    out = web.top_recipe(str(args.get("query", "")))
                else:
                    out = core.run_tool(store, t.function.name, args)
                failed = "오류" in out
                summary = web.summarize(out) if t.function.name == web.TOOL_SPEC["name"] \
                    else core.summarize(t.function.name, out)
                log.append({"도구": t.function.name, "인자": args, "상태": "실패" if failed else "성공",
                            "요약": summary})
                if not failed:
                    results.append({"도구": t.function.name, "인자": args, "결과": out})
                msgs.append({"role": "tool", "tool_call_id": t.id, "content": json.dumps(out, ensure_ascii=False)})
    except Exception as e:  # 네트워크, 시간 초과, 인증, 모델 오류 등은 모두 모델 호출 실패
        name = type(e).__name__
        return {"text": "", "log": log, "results": results,
                "error": {"kind": "모델 실패", "message": f"모델 호출에 실패했습니다 ({name}). 다시 시도해 주세요."}}
