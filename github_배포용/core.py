"""냉장고 식단 에이전트 - 데이터 검증, 계산, 도구 함수. 수량 계산은 모두 이 파일의 코드가 한다."""
import csv
import io
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
UNITS = ("g", "개")


class DataError(Exception):
    """파일 오류. messages에 원인과 위치를 담는다."""

    def __init__(self, messages):
        super().__init__("; ".join(messages))
        self.messages = messages


def num(x):
    """부동소수 잡음만 제거하고 반올림은 하지 않는다 (4.5 -> 4.5)."""
    x = round(float(x), 6)
    return int(x) if x == int(x) else x


def _read_text(src):
    raw = src.read_bytes() if isinstance(src, Path) else src
    return raw.decode("utf-8-sig")


def load_fridge(src):
    """냉장고 CSV -> 재료 목록. 오류가 있으면 빈 재고로 대체하지 않고 DataError."""
    try:
        text = _read_text(src)
    except UnicodeDecodeError:
        raise DataError(["냉장고 CSV: UTF-8로 읽을 수 없습니다."])
    rows = list(csv.DictReader(io.StringIO(text)))
    need = {"재료ID", "이름", "수량", "단위"}
    if not rows or not need <= set(rows[0].keys()):
        raise DataError(["냉장고 CSV: 헤더(재료ID,이름,수량,단위)가 없거나 데이터가 비어 있습니다."])
    errors, seen, items = [], {}, []
    for i, r in enumerate(rows, start=2):  # 헤더가 1행
        rid, name = (r["재료ID"] or "").strip(), (r["이름"] or "").strip()
        if not rid or not name:
            errors.append(f"{i}행: 재료ID 또는 이름이 비어 있습니다.")
            continue
        if rid in seen:
            errors.append(f"{i}행: 재료ID {rid}가 중복됩니다 ({seen[rid]}행에도 있음).")
            continue
        seen[rid] = i
        try:
            q = float(r["수량"])
            if q < 0 or q != q:
                raise ValueError
        except (ValueError, TypeError):
            if (r["수량"] or "").strip().lstrip("-").replace(".", "", 1).isdigit():
                errors.append(f"{i}행: {name}({rid}) 수량 {r['수량']}은 0 이상이어야 합니다.")
            else:
                errors.append(f"{i}행: {name}({rid}) 수량 '{r['수량']}'이 숫자가 아닙니다.")
            continue
        unit = (r["단위"] or "").strip()
        if unit not in UNITS:
            errors.append(f"{i}행: {name}({rid}) 단위 '{unit}'은 g 또는 개여야 합니다.")
            continue
        items.append({"재료ID": rid, "이름": name, "수량": num(q), "단위": unit})
    if errors:
        raise DataError(errors)
    return items


def load_recipes(src):
    """레시피 JSON -> 레시피 목록. 형식이 깨지면 DataError."""
    try:
        data = json.loads(_read_text(src))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise DataError([f"레시피 JSON을 읽을 수 없습니다 ({e})."])
    if not isinstance(data, list) or not data:
        raise DataError(["레시피 JSON: 최상위가 레시피 목록(배열)이어야 합니다."])
    errors, ids = [], set()
    for n, r in enumerate(data, start=1):
        if not isinstance(r, dict):
            errors.append(f"{n}번째 레시피: 객체가 아닙니다.")
            continue
        label = f"{r.get('레시피ID', n)} {r.get('이름', '')}".strip()
        for k in ("레시피ID", "이름", "기준인원", "재료", "조리순서"):
            if k not in r:
                errors.append(f"{label}: '{k}' 항목이 없습니다.")
        if "레시피ID" in r:
            if r["레시피ID"] in ids:
                errors.append(f"{label}: 레시피ID가 중복됩니다.")
            ids.add(r["레시피ID"])
        b = r.get("기준인원")
        if "기준인원" in r and not (isinstance(b, int) and not isinstance(b, bool) and b >= 1):
            errors.append(f"{label}: 기준인원 오류({b}) - 1 이상의 정수여야 합니다.")
        if isinstance(r.get("재료"), list):
            for ing in r["재료"]:
                ok = isinstance(ing, dict) and all(k in ing for k in ("재료ID", "이름", "수량", "단위"))
                if not ok:
                    errors.append(f"{label}: 재료 항목 형식 오류 {ing}")
                elif ing["단위"] not in UNITS or not isinstance(ing["수량"], (int, float)) or ing["수량"] < 0:
                    errors.append(f"{label}: 재료 {ing.get('이름')}의 수량/단위 오류.")
        elif "재료" in r:
            errors.append(f"{label}: '재료'가 목록이 아닙니다.")
    if errors:
        raise DataError(errors)
    return data


class Store:
    """현재 사용 중인 재고와 레시피. 오류가 있으면 errors에 담고 도구는 사용할 수 없다."""

    def __init__(self, fridge_src=None, recipe_src=None):
        self.fridge, self.recipes, self.errors = [], [], []
        try:
            self.fridge = load_fridge(fridge_src or DATA_DIR / "냉장고.csv")
        except DataError as e:
            self.errors += e.messages
        try:
            self.recipes = load_recipes(recipe_src or DATA_DIR / "레시피.json")
        except DataError as e:
            self.errors += e.messages

    @property
    def ok(self):
        return not self.errors

    def stock(self, ing):
        """레시피 재료에 해당하는 냉장고 항목(재료ID 우선, 이름 보조)."""
        for it in self.fridge:
            if it["재료ID"] == ing["재료ID"] or it["이름"] == ing["이름"]:
                return it
        return None

    def recipe(self, rid):
        """레시피ID로 찾고, 모델이 이름을 넘긴 경우에도 같은 레시피로 해석한다."""
        return next((r for r in self.recipes if r["레시피ID"] == rid or r["이름"] == rid), None)


# ---------------------------------------------------------------- 도구 함수
def _need_ok(store):
    if not store.ok:
        return {"오류": "데이터 파일 오류로 계산할 수 없습니다.", "상세": store.errors}
    return None


def get_inventory(store, name=None):
    if (e := _need_ok(store)):
        return e
    items = store.fridge
    if name:
        items = [i for i in items if name.strip() in i["이름"] or i["이름"] in name.strip()]
        if not items:
            return {"조회": name, "결과": "냉장고에 없는 재료입니다 (보유 0).", "재료": []}
    return {"재료": items}


def list_recipes(store):
    if (e := _need_ok(store)):
        return e
    out = []
    for r in store.recipes:
        out.append({
            "레시피ID": r["레시피ID"], "이름": r["이름"], "기준인원": r["기준인원"],
            "재료": [{"이름": i["이름"], "수량": i["수량"], "단위": i["단위"],
                      **({} if store.stock(i) else {"비고": "미등록, 보유 0으로 비교"})}
                     for i in r["재료"]],
        })
    return {"메뉴수": len(out), "메뉴": out}


def calculate(store, recipe_id, servings):
    """필요량 = 기준량 x 인원 / 기준인원, 부족량 = max(필요 - 보유, 0). 단위가 다르면 보류."""
    if (e := _need_ok(store)):
        return e
    r = store.recipe(recipe_id)
    if r is None:
        return {"오류": f"등록되지 않은 레시피ID: {recipe_id}"}
    if not isinstance(servings, (int, float)) or isinstance(servings, bool) or servings <= 0:
        return {"오류": f"인원은 1 이상이어야 합니다: {servings}"}
    rows, shopping, held = [], [], []
    for ing in r["재료"]:
        need = ing["수량"] * servings / r["기준인원"]
        st = store.stock(ing)
        row = {"재료": ing["이름"], "단위": ing["단위"], "필요": num(need)}
        if st is None:
            row.update(보유=0, 부족=num(need), 비고="미등록, 보유 0으로 비교")
        elif st["단위"] != ing["단위"]:
            row.update(보유=f"{st['수량']}{st['단위']}", 부족=None,
                       비고=f"단위 불일치({st['단위']} ≠ {ing['단위']}), 계산 보류")
            held.append(ing["이름"])
        else:
            row.update(보유=st["수량"], 부족=num(max(need - st["수량"], 0)))
        rows.append(row)
        if row["부족"]:
            shopping.append({"재료": ing["이름"], "수량": row["부족"], "단위": ing["단위"]})
    return {
        "레시피ID": r["레시피ID"], "메뉴": r["이름"], "인원": servings, "기준인원": r["기준인원"],
        "표": rows, "장보기": shopping, "계산보류": held,
        "장보기확정": not held,
        "안내": ("보류된 재료가 있어 장보기를 확정할 수 없습니다." if held
                 else ("추가로 필요한 재료가 없습니다." if not shopping else "")),
        "재고변경": "현재 재고는 변경되지 않습니다.",
    }


def search_recipes(store, servings, exclude_ingredients=None, only_available=False):
    """제외 재료가 든 메뉴를 빼고, 코드 계산으로 가능/부족을 판정해 최대 3개 후보를 낸다."""
    if (e := _need_ok(store)):
        return e
    if not isinstance(servings, (int, float)) or servings <= 0:
        return {"오류": "인원(servings)이 필요합니다. 몇 명인지 사용자에게 물어보세요."}
    ex = [x.strip() for x in (exclude_ingredients or []) if x.strip()]
    cands = []
    for r in store.recipes:
        if any(x == i["이름"] or x in i["이름"] for x in ex for i in r["재료"]):
            continue
        c = calculate(store, r["레시피ID"], servings)
        short = [s for s in c["장보기"]]
        held = c["계산보류"]
        feasible = not short and not held
        if only_available and not feasible:
            continue
        cands.append({
            "레시피ID": r["레시피ID"], "메뉴": r["이름"], "인원": servings,
            "판정": "가능" if feasible else ("계산 보류" if held and not short else "부족"),
            "부족": short, "계산보류": held,
            "재료": [f"{i['이름']} {num(i['수량'] * servings / r['기준인원'])}{i['단위']}" for i in r["재료"]],
        })
    cands.sort(key=lambda c: (c["판정"] != "가능", len(c["부족"]) + len(c["계산보류"])))
    cands = cands[:3]
    out = {"조건": {"인원": servings, "제외재료": ex, "있는재료만": only_available}, "후보": cands}
    if not cands:
        out["안내"] = "조건에 맞는 후보가 없습니다. 조건을 바꿀지 사용자에게 물어보세요."
    return out


def get_steps(store, recipe_id):
    if (e := _need_ok(store)):
        return e
    r = store.recipe(recipe_id)
    if r is None:
        return {"오류": f"등록되지 않은 레시피ID: {recipe_id}"}
    return {"레시피ID": r["레시피ID"], "메뉴": r["이름"], "조리순서": r["조리순서"]}


TOOL_SPECS = [
    {"name": "get_inventory", "description": "냉장고 보유 재료를 조회한다. name을 주면 그 재료만, 없으면 전체.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "재료 이름(예: 쌀)"}}}},
    {"name": "list_recipes", "description": "등록된 메뉴(레시피) 목록과 기준 분량을 조회한다.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "search_recipes",
     "description": "인원과 제외 재료에 맞는 메뉴 후보(최대 3개)를 찾고 가능/부족을 판정한다. 인원을 모르면 호출하지 말고 사용자에게 물어본다.",
     "parameters": {"type": "object", "properties": {
         "servings": {"type": "number", "description": "먹는 인원"},
         "exclude_ingredients": {"type": "array", "items": {"type": "string"}, "description": "빼고 싶은 재료 이름"},
         "only_available": {"type": "boolean", "description": "'있는 재료만'일 때 true"}},
         "required": ["servings"]}},
    {"name": "calculate_recipe",
     "description": "레시피ID와 인원으로 재료별 필요/보유/부족과 장보기 목록을 계산한다. 수량은 직접 계산하지 않는다.",
     "parameters": {"type": "object", "properties": {
         "recipe_id": {"type": "string"}, "servings": {"type": "number"}},
         "required": ["recipe_id", "servings"]}},
    {"name": "get_recipe_steps", "description": "레시피 원문 조리 순서를 조회한다.",
     "parameters": {"type": "object", "properties": {"recipe_id": {"type": "string"}}, "required": ["recipe_id"]}},
]


def run_tool(store, name, args):
    if name == "get_inventory":
        return get_inventory(store, args.get("name"))
    if name == "list_recipes":
        return list_recipes(store)
    if name == "search_recipes":
        return search_recipes(store, args.get("servings"), args.get("exclude_ingredients"),
                              bool(args.get("only_available", False)))
    if name == "calculate_recipe":
        return calculate(store, args.get("recipe_id"), args.get("servings"))
    if name == "get_recipe_steps":
        return get_steps(store, args.get("recipe_id"))
    return {"오류": f"알 수 없는 도구: {name}"}


def summarize(name, result):
    """도구 실행 기록에 보여 줄 한 줄 요약."""
    if "오류" in result:
        return f"실패: {result['오류']}"
    if name == "get_inventory":
        return ", ".join(f"{i['이름']} {i['수량']}{i['단위']}" for i in result["재료"]) or result.get("결과", "")
    if name == "list_recipes":
        return f"메뉴 {result['메뉴수']}개: " + ", ".join(m["이름"] for m in result["메뉴"])
    if name == "search_recipes":
        return "후보: " + (", ".join(f"{c['메뉴']}({c['판정']})" for c in result["후보"]) or "없음")
    if name == "calculate_recipe":
        return f"{result['메뉴']} {result['인원']}명 - 장보기 " + (
            ", ".join(f"{s['재료']} {s['수량']}{s['단위']}" for s in result["장보기"]) or "없음")
    if name == "get_recipe_steps":
        return f"{result['메뉴']} 조리순서 {len(result['조리순서'])}단계"
    return ""
