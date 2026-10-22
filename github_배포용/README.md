# 🧊 냉장고 식단 에이전트

냉장고 재료로 만들 수 있는 메뉴를 추천하고, 인원에 맞춘 필요량·부족량을 계산하는 Streamlit 챗봇입니다.
재료·메뉴를 물으면 만개의레시피(10000recipe.com) 추천순 1위 레시피 정보와 원문 링크도 안내합니다.

## 실행

```bash
pip install -r requirements.txt
copy .env.example .env   # 열어서 OPENAI_API_KEY, OPENAI_MODEL 입력
python -m streamlit run app.py
```

## 구성
- `app.py` 화면(냉장고 그림 클릭 → 업로드, 추천, 챗봇, 질문 기록)
- `agent.py` OpenAI tool-calling 에이전트
- `core.py` 데이터 검증과 수량 계산(계산은 코드가 수행)
- `web.py` 만개의레시피 조회
- `data/` 교육용 냉장고·레시피 데이터, `data/오류/` 오류 시험용 파일

데이터는 수업용 교육용 자료이며 식품 안전·영양 적합성을 검증하지 않았습니다. 재료 제외는 선호 반영일 뿐 알레르기 안전을 보장하지 않습니다.
만개의레시피 내용은 링크로만 안내하며, 해당 사이트의 저작권은 각 작성자와 사이트에 있습니다.
