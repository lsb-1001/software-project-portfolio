import re
import joblib
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Any

# 1. 한글 정리 함수 (변경 없음)
def clean_korean_text(text: str) -> str:
    text = re.sub(r"[^\u1100-\u11FF\uAC00-\uD7A3a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# 2. 정규식 패턴 생성 (글자 사이 특수문자 허용 횟수 최소화)
def make_swear_pattern(swear: str) -> str:
    # **개선:** 글자 사이에 들어갈 수 있는 특수문자/공백의 최대 횟수를 0~1회로 제한
    # (원래: r"[\s0-9\W_]*" -> 변경: r"[\s0-9\W_]{0,1}" 또는 r"[\s\W]{0,1}"
    # 여기서는 좀 더 엄격하게 공백이나 비문자(특수문자)를 0~1개만 허용
    pattern = r"[\s\W]{0,1}".join([re.escape(ch) for ch in swear])
    return pattern


# 3. 욕설 사전 리스트 (변경 없음)
SWEAR_SEVERITY: Dict[str, List[str]] = {
    "low": [
        "노답", "꼴통", "싸가지", "싸가지없", "상놈", "버러지", "벌레", "쓰레기", "도랏", "관종", "트롤", "피지알",
        "가정교육", "급식", "중졸", "무식한", "생긴거봐", "얼굴값", "능지", "뇌절", "천치", "머갈", "멍청이", "바보", "찐따", "루저"
    ],
    "mid": [
        "미친놈", "미친년", "미친새끼", "미친", "미ㅊ", "미쳣", "미췬", "또라이", "돌아이", "돌았냐", "또라이라서", "또라이다", "미쵸", "미쳤냐",
        "정신병자", "정신 나감", "새끼", "색히", "새키", "쌔끼", "쌔키", "쎄끼", "쌕희", "새뀌", "쌔뀌", "쌕끼", "쌩끼", "샛기", "샠기",
        "지랄", "지롤", "지뢀", "쥐랄", "쥐롤", "지랄맞은", "지랄병", "염병", "엠병", "얌병", "영병", "열병", "염병할", "염뵹", "욤병", "욤뵹",
        "개같", "개년", "개놈", "개지랄", "개소리", "망할놈", "망할년", "틀딱", "급식충","씨뇨", "현피"
    ],
    "high": [
        "병신", "빙신", "븅신", "병ㅅ", "벼엉신", "변신", "뵹신", "씨발", "ㅅㅂ", "ㅆㅂ", "시발", "쉬발", "시바", "쉬바", "씨바", "씨팔", "씨벌", "씨뻘", "씌벌", "씌팔",
        "좆", "존나", "좃", "좆같", "좇", "졷", "죶", "좆밥", "좆만", "좆병신", "좆노답", "좆만이", "좇같", "좃가튼", "좆같은년",
        "씹", "씹새끼", "씹년", "씹할", "씹놈", "씹보지", "씹덕", "씹선비", "씹장애", "씹창", "씹쌔끼", "씹팔", "씹벌", "씹스러운", "씹덕후",
        "보지", "보지년", "자지", "찌찌", "젖꼭지", "가슴크네", "섹스", "색스", "쎅스", "애무", "딸딸이", "딸치기",
        "후레자식", "후레년", "후레놈", "장애인새끼", "패드립", "엄마없냐", "아버지없냐", "애미뒤짐", "애비뒤짐", "부랄",
        "한남", "한녀", "김치녀", "김치남", "된장녀", "흑형", "흑인놈", "백인놈", "양놈", "짱깨", "쪽바리", "메갈", "워마드", "일베충", "대깨문",
        "개새끼", "개색기", "개쉐이", "개색히", "개새키", "개병신", "개또라이", "개븅신", "개좆", "개족같", "개노답", "개븅"
    ]
}

base_swears: List[str] = (
    SWEAR_SEVERITY["low"]
    + SWEAR_SEVERITY["mid"]
    + SWEAR_SEVERITY["high"]
)

# 4. 초성 욕설만 필터링 (변경 없음)
initial_consonant_swears: List[str] = [swear for swear in base_swears if re.fullmatch(r'[ㄱ-ㅎ]{2,}', swear)]

# 5. 후처리 함수 (ML 예측이 0일 때만 사전을 통한 재검토)
def postprocess_prediction(text: str, prediction: int, base_swears: list) -> int:
    # **개선:** ML 모델의 예측 (prediction)이 0일 때만 사전 검사를 통해 1로 상향 조정
    if prediction == 1:
        return 1

    lowered_text = text.lower()

    for swear in base_swears:
        pattern = make_swear_pattern(swear)
        # re.IGNORECASE는 make_swear_pattern의 escape 때문에 필요 없으므로 제거 (이미 lowered_text 사용)
        if re.search(pattern, lowered_text):
            return 1

    return 0

# 5. 욕설 점수 계산 함수 (ML 가중치 상향 및 severity 누적 반영)
def calculate_swear_score(text: str, ml_proba: float) -> float:
    
    # 누적 가산 로직
    base_severity_score = 0.0
    regex_hit = False
    lowered_text = text.lower()
    severity_weights = {"low": 0.15, "mid": 0.4, "high": 0.7}
    
    # 가장 높은 탐지 레벨을 추적 (가중치 제한에 사용)
    max_level_weight = 0.0 

    for level, swear_list in SWEAR_SEVERITY.items():
        weight = severity_weights[level]
        for swear in swear_list:
            pattern = make_swear_pattern(swear)
            matches = re.findall(pattern, lowered_text)
            
            if matches:
                # 발견된 욕설 개수만큼 가중치를 누적
                base_severity_score += weight * len(matches)
                regex_hit = True
                max_level_weight = max(max_level_weight, weight)

    # 누적된 base_severity_score 정규화
    normalized_severity = min(base_severity_score / 1.5, 1.0) 
    
    # **핵심 수정: ML 가중치 동적 조정**
    ml_weight = 0.45 
    
    # Low 수준의 욕설(max_level_weight <= 0.15)만 탐지된 경우, ML 가중치를 낮춤
    if max_level_weight <= 0.15: 
        ml_weight = 0.25 
    
    # 최종 점수 계산 (가중 평균)
    final_score = (
        ml_weight * ml_proba + 
        (1.0 - ml_weight) * normalized_severity 
    )

    return round(min(final_score, 1.0), 3)

# 6. 이벤트 루프 중첩 방지 (변경 없음)


# 7. FastAPI 앱 초기화 (변경 없음)
app = FastAPI()

# 8. CORS 설정 (변경 없음)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 9. 모델과 벡터라이저 로드 (변경 없음)
MODEL_DIR = Path(__file__).resolve().parent
# 모델이 없으면 시작을 중단합니다. 더미 결과를 실제 추론처럼 반환하지 않습니다.
model: Any = joblib.load(MODEL_DIR / "profanity_lr_model.pkl")
vectorizer: Any = joblib.load(MODEL_DIR / "tfidf_vectorizer.pkl")

# 10. 요청 바디 구조 (변경 없음)
class TextRequest(BaseModel):
    text: str

# 11. API 엔드포인트 (변경 없음)
@app.post("/detect")
def detect_swear(req: TextRequest):
    X = vectorizer.transform([req.text])
    prediction = model.predict(X)[0]
    proba = model.predict_proba(X)[0][1]

    final_label = postprocess_prediction(req.text, prediction, base_swears)
    swear_score = calculate_swear_score(req.text, proba)
    return {
        "text": req.text,
        "is_swear": bool(final_label),
        "swear_score" : swear_score,
        "level": (
            "low" if swear_score < 0.3 else
            "mid" if swear_score < 0.6 else
            "high" if swear_score < 0.85 else
            "critical"
        )
    }

# 12. 로컬 실행 설정
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)