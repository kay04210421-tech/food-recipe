"""만개의레시피 추천순 1위 레시피 조회. 제목·링크·기본 정보·재료만 가져오고, 조리 과정은 원문 링크로 안내한다."""
import html
import re
from functools import lru_cache
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "https://www.10000recipe.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (fridge-agent classroom demo)"}

TOOL_SPEC = {
    "name": "search_web_recipe",
    "description": "만개의레시피(10000recipe.com)에서 재료나 메뉴 이름으로 검색해 '추천순' 첫 번째 레시피를 가져온다. "
                   "사용자가 직접 말한 재료/메뉴로 레시피를 찾거나 만개의레시피를 언급할 때 쓴다. 냉장고 재고 조회와는 별개다.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "검색어. 재료는 공백으로 구분(예: '감자 당근 양파') 또는 메뉴 이름"}},
        "required": ["query"]},
}


def _get(url):
    with urlopen(Request(url, headers=HEADERS), timeout=15) as r:
        return r.read().decode("utf-8", "replace")


def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


@lru_cache(maxsize=64)
def top_recipe(query):
    q = query.strip()
    if not q:
        return {"오류": "검색어가 비어 있습니다."}
    try:
        page = _get(f"{BASE}/recipe/list.html?q={quote(q)}&order=reco&page=1")
        m = re.search(r'href="(/recipe/(\d+))"', page)
        if not m:
            return {"오류": f"만개의레시피에서 '{q}' 검색 결과가 없습니다."}
        url = BASE + m.group(1)
        d = _get(url)
    except Exception as e:
        return {"오류": f"만개의레시피에 접속하지 못했습니다 ({type(e).__name__})."}

    title = _clean((re.search(r'<meta property="og:title" content="([^"]+)"', d) or [None, ""])[1])
    info = [_clean(x.group(1)) for x in re.finditer(r'class="view2_summary_info\d">([^<]+)', d)]
    start = d.find('id="divConfirmedMaterialArea"')
    end = d.find("view_step", start)
    seg = d[start:end if end > start else start + 8000]
    ingredients = []
    for li in re.finditer(r'class="ingre_list_name">(.*?)</div>\s*<span class="ingre_list_ea">([^<]*)', seg, re.S):
        name, amount = _clean(li.group(1)), _clean(li.group(2))
        if name:
            ingredients.append({"재료": name, "분량": amount})
    return {
        "검색어": q, "정렬": "추천순 1위", "제목": title, "링크": url,
        "정보": " · ".join(info), "재료": ingredients,
        "출처": "만개의레시피 (조리 과정은 링크에서 확인)",
    }


def summarize(result):
    if "오류" in result:
        return f"실패: {result['오류']}"
    return f"{result['제목']} (재료 {len(result['재료'])}개) {result['링크']}"
