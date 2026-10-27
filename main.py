"""
MyBoard 백엔드 FastAPI 서버

기능:
  1. 사용자 인증 (회원가입, 로그인, 로그아웃)
  2. 게시글 관리 (생성, 조회, 삭제)
  3. 댓글 관리 (생성, 조회, 삭제)
  4. 권한 검사 (로그인 여부, 작성자/관리자 확인)
  5. 조회수 추적
  6. 욕설 필터링 (외부 AI 서버 연동)

요구사항 구현:
  ✓ 각 글에 조회수와 작성자명 표시
  ✓ 로그인한 사용자만 글 작성 가능
  ✓ 각 사용자는 자신의 글/댓글만 삭제 가능
  ✓ system 계정은 관리자 - 모든 글/댓글 삭제 가능
  ✓ 공지사항은 관리자(system)만 작성 가능
"""

from fastapi import FastAPI, HTTPException, Depends, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import sqlite3
import os
import requests
from datetime import datetime
import hashlib
import secrets
import re

app = FastAPI()

# ===============================================
# 설정
# ===============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get("BOARD_DATABASE", os.path.join(BASE_DIR, "database.db"))

# AI 서버(욕설 감지) - 로컬 API 서버 사용 (API/main.py가 8090 포트에서 실행)
API_BASE_DETECT = "http://127.0.0.1:8090/detect"
ACTIVE_API = 'local'

# 필터링 레벨 설정 (관리자 설정 가능)
FILTERING_LEVELS = ['none', 'low', 'mid', 'high']
FILTERING_LEVEL_SETTING = 'none'  # 기본값: 필터링 안함

@app.get('/active_api')
def active_api():
    """현재 사용 중인 마스킹/감지 API 정보 반환"""
    return {"active": ACTIVE_API, "detect_endpoint": API_BASE_DETECT}

@app.get('/filtering_level')
def get_filtering_level():
    """현재 필터링 레벨 설정 반환"""
    return {"level": FILTERING_LEVEL_SETTING, "available_levels": FILTERING_LEVELS}

@app.post('/filtering_level')
def set_filtering_level(data: dict, session_token: str = Cookie(None)):
    """필터링 레벨 설정 (관리자만)"""
    global FILTERING_LEVEL_SETTING
    user = get_current_user(session_token)
    if not user or user["username"] != "system":
        raise HTTPException(status_code=403, detail="관리자만 설정할 수 있습니다.")
    
    level = data.get('level')
    if level not in FILTERING_LEVELS:
        raise HTTPException(status_code=400, detail=f"유효한 레벨: {FILTERING_LEVELS}")
    
    FILTERING_LEVEL_SETTING = level
    print(f"🔧 필터링 레벨 변경: {level}")
    return {"status": "success", "level": level}

@app.post('/analyze')
async def analyze_text(data: dict):
    """텍스트의 욕설 점수와 단계를 분석해 반환합니다 (마스킹 없음)"""
    text = data.get('text', '')
    if not text:
        return {"text": "", "is_swear": False, "swear_score": 0.0, "level": "none"}
    
    try:
        resp = requests.post(API_BASE_DETECT, json={"text": text}, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            return {
                "text": result.get('text', text),
                "is_swear": result.get('is_swear', False),
                "swear_score": float(result.get('swear_score', 0.0)),
                "level": result.get('level', 'none')
            }
    except Exception as e:
        print(f"⚠️ 분석 API 오류: {e}")
    
    return {"text": text, "is_swear": False, "swear_score": 0.0, "level": "none"}

# ===============================================
# 미들웨어 설정
# ===============================================
# CORS 활성화: 모든 오리진에서 요청 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 마운트: /static 경로의 HTML, CSS, JS 등 제공
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ===============================================
# HTML 페이지 라우트
# ===============================================
@app.get("/")
async def get_index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

@app.get("/index.html")
async def get_index_html():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

@app.get("/write.html")
async def get_write():
    return FileResponse(os.path.join(BASE_DIR, "static", "write.html"))

@app.get("/post.html")
async def get_post_page():
    return FileResponse(os.path.join(BASE_DIR, "static", "post.html"))

@app.get("/category.html")
async def get_category():
    return FileResponse(os.path.join(BASE_DIR, "static", "category.html"))

@app.get("/register.html")
async def get_register():
    return FileResponse(os.path.join(BASE_DIR, "static", "register.html"))

@app.get("/login.html")
async def get_login():
    return FileResponse(os.path.join(BASE_DIR, "static", "login.html"))

@app.get("/admin.html")
async def get_admin():
    return FileResponse(os.path.join(BASE_DIR, "static", "admin.html"))

class Post(BaseModel):
    title: str
    content: str
    category: str
    is_notice: bool = False

class Comment(BaseModel):
    post_id: int
    content: str

class User(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

# ===============================================
# DB 스키마 정의
# ===============================================
# posts 테이블: 게시글 정보
#   - id: 고유 ID (자동 증가)
#   - title: 제목
#   - content: 내용 (욕설 필터링됨)
#   - category: 카테고리 ('공지', '자유', '질문')
#   - is_notice: 공지 여부 (0 또는 1)
#   - created_at: 작성 시간
#   - author: 작성자 (username)
#   - views: 조회수 (자동 증가)

# comments 테이블: 댓글 정보
#   - id: 고유 ID (자동 증가)
#   - post_id: 게시글 ID (외래키)
#   - content: 댓글 내용 (욕설 필터링됨)
#   - created_at: 작성 시간
#   - author: 작성자 (username)

# users 테이블: 사용자 정보
#   - id: 고유 ID (자동 증가)
#   - username: 사용자명 (유일)
#   - password: SHA256 해시된 비밀번호
#   - email: 이메일 (유일)
#   - created_at: 가입 시간

def create_tables_if_missing():
    """DB 테이블 생성 (테이블이 없을 때만)"""
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    
    # posts 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT '자유',
            is_notice INTEGER DEFAULT 0,
            created_at TEXT,
            author TEXT,
            views INTEGER DEFAULT 0
        )
    """)
    
    # comments 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            content TEXT NOT NULL,
            created_at TEXT,
            author TEXT,
            FOREIGN KEY (post_id) REFERENCES posts(id)
        )
    """)
    
    # users 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def ensure_column(table: str, column: str, definition: str):
    """
    기존 테이블에 컬럼이 없으면 추가
    (DB 마이그레이션용)
    """
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    
    # 현재 테이블의 컬럼 목록 조회
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    
    # 컬럼이 없으면 추가
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()
    conn.close()


def migrate_schema():
    """
    기존 DB에 새로운 컬럼 추가
    (서버 시작 시 자동 실행)
    """
    ensure_column('posts', 'author', "TEXT")
    ensure_column('posts', 'views', "INTEGER DEFAULT 0")
    ensure_column('posts', 'swear_score', "REAL DEFAULT 0.0")
    ensure_column('posts', 'swear_level', "TEXT DEFAULT 'none'")
    # store original unmasked content to allow dynamic filtering/unmasking
    ensure_column('posts', 'raw_content', "TEXT")
    ensure_column('comments', 'author', "TEXT")
    ensure_column('comments', 'created_at', "TEXT")
    ensure_column('comments', 'swear_score', "REAL DEFAULT 0.0")
    ensure_column('comments', 'swear_level', "TEXT DEFAULT 'none'")
    ensure_column('comments', 'raw_content', "TEXT")


# 서버 시작 시 스키마 마이그레이션 및 테이블 생성
create_tables_if_missing()
migrate_schema()

# ===============================================
# 비밀번호 해시 함수
# ===============================================
def hash_password(password: str) -> str:
    """비밀번호를 해시합니다."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash: str, provided_password: str) -> bool:
    """제공된 비밀번호가 저장된 해시와 일치하는지 확인합니다."""
    return stored_hash == hash_password(provided_password)

# ===============================================
# 인증 관련 함수
# ===============================================
# 세션 저장소: 메모리 기반 (실제 운영 환경에서는 Redis 권장)
# 키: session_token, 값: {'user_id': int, 'username': str}
SESSIONS = {}


def create_session_token():
    """새로운 세션 토큰 생성 (64자리 16진수)"""
    return secrets.token_hex(32)


def get_current_user(session_token: str = Cookie(None)):
    """
    쿠키에서 세션 토큰을 읽고 현재 사용자 정보 반환
    
    반환값:
      - 로그인됨: {'user_id': int, 'username': str}
      - 로그인 안 됨: None
    """
    if not session_token or session_token not in SESSIONS:
        return None
    return SESSIONS[session_token]

# ===============================================
# Helper 함수: 욕설 감지 API 호출 및 내용 치환
# ===============================================
def censor_content(original_content: str, use_ml: bool = False):
    """
    외부 AI 서버에 텍스트를 전송하고, 감지된 욕설을 '*'로 치환
    필터링 레벨에 따라 마스킹 여부 결정
    
    동작:
      1. AI 서버(/detect)로 점수/단계 감지
      2. 로컬 마스킹으로 욕설 문자 처리
      3. 필터링 레벨에 따라 마스킹 적용 여부 판단
      4. 원본 텍스트 + (점수, 단계) 반환 (마스킹은 읽을 때 동적으로 적용)
    
    인자:
      original_content: 원본 텍스트
      use_ml: ML 기반 마스킹 사용 여부 (미사용)
    
    반환값:
      (원본_텍스트, 욕설_점수, 욕설_단계)
      주의: 마스킹된 텍스트가 아닌 원본을 반환합니다.
            마스킹은 apply_dynamic_filtering()에서 읽을 때 적용됩니다.
    """
    if not original_content:
        return (original_content, 0.0, 'none')
    
    try:
        # 1) /detect로 점수와 단계 감지
        swear_score = 0.0
        swear_level = 'none'
        try:
            dresp = requests.post(API_BASE_DETECT, json={"text": original_content}, timeout=10)
            if dresp.status_code == 200:
                ddata = dresp.json()
                if isinstance(ddata, dict):
                    swear_score = float(ddata.get('swear_score', 0.0))
                    swear_level = ddata.get('level', 'none')
        except Exception as e:
            print(f"⚠️ /detect 호출 오류: {e}")
        
        # 원본 텍스트와 점수/단계만 반환 (마스킹은 읽을 때 동적으로 적용)
        return (original_content, swear_score, swear_level)
    except Exception as e:
        print(f"❌ censor_content 처리 중 오류: {e}")
        return (original_content, 0.0, 'none')

def apply_dynamic_filtering(content: str, swear_score: float, swear_level: str) -> str:
    """
    저장된 콘텐츠와 욕설 메타데이터(점수, 단계)를 받아
    현재 필터링 레벨에 따라 동적으로 마스킹을 적용하거나 제거
    
    필터링 로직:
      FILTERING_LEVEL_SETTING이 높을수록 더 많이 마스킹함
      예: 'high'로 설정되면 low/mid/high 욕설 모두 마스킹
          'none'으로 설정되면 마스킹 안 함
    
    인자:
      content: 원본 내용 (DB에 저장된 값)
      swear_score: 욕설 점수 (0~1)
    swear_level: 욕설 단계 (none/low/mid/high)
    
    반환값:
      필터링이 적용된 텍스트 (또는 필터링이 필요 없으면 원본)
    """
    # 욕설이 없으면 원본 반환
    if not content or swear_level == 'none':
        return content
    
    # 필터링 설정이 'none'이면 마스킹 안 함
    if FILTERING_LEVEL_SETTING == 'none':
        return content
    
    # 필터링 레벨 체크
    # 올바른 로직:
    # FILTERING_LEVEL_SETTING='low'(1)이면 low(1) 이상의 욕설 모두 마스킹
    # FILTERING_LEVEL_SETTING='mid'(2)이면 mid(2) 이상의 욕설만 마스킹
    # 예: FILTERING_LEVEL_SETTING='low'일 때,
    #     swear_level='low'(1)은 1 <= 1이므로 마스킹
    #     swear_level='high'(3)은 3 <= 1이 아니므로... 아니, 반대!
    #     swear_level='high'(3) >= FILTERING_LEVEL_SETTING(1)이므로 마스킹
    level_order = {'none': 0, 'low': 1, 'mid': 2, 'high': 3}
    current_level_value = level_order.get(swear_level, 0)
    filter_level_value = level_order.get(FILTERING_LEVEL_SETTING, 0)
    
    # 현재 욕설 단계 >= 필터링 레벨이면 마스킹 적용
    # (필터링 레벨 이상의 모든 욕설을 마스킹)
    if current_level_value >= filter_level_value:
        # 로컬 마스킹 수행
        try:
            with open(os.path.join(BASE_DIR, 'swearing_words.txt'), 'r', encoding='utf-8') as f:
                swear_list = [w.strip() for w in f.readlines() if w.strip()]
        except Exception:
            return content
        
        result_chars = list(content)
        try:
            for swear in swear_list:
                parts = []
                for ch in swear:
                    parts.append(re.escape(ch))
                pattern = re.compile(r'[\W_0-9]{0,3}'.join(parts), re.IGNORECASE)
                for m in pattern.finditer(content):
                    for i in range(m.start(), m.end()):
                        if result_chars[i] != ' ':
                            result_chars[i] = '*'
        except Exception:
            return content
        
        return ''.join(result_chars)
    
    return content


# ===============================================
# 인증 API (회원가입, 로그인, 로그아웃)
# ===============================================
@app.post("/register")
async def register(user: User):
    """회원가입 엔드포인트"""
    
    # 입력값 검증
    if len(user.username) < 3:
        raise HTTPException(status_code=400, detail="사용자명은 최소 3자 이상이어야 합니다.")
    
    if len(user.password) < 6:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 6자 이상이어야 합니다.")
    
    if "@" not in user.email:
        raise HTTPException(status_code=400, detail="유효한 이메일을 입력하세요.")
    
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    
    # 기존 사용자 확인
    cur.execute("SELECT id FROM users WHERE username = ?", (user.username,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="이미 존재하는 사용자명입니다.")
    
    cur.execute("SELECT id FROM users WHERE email = ?", (user.email,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")
    
    # 새 사용자 등록
    try:
        password_hash = hash_password(user.password)
        cur.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (user.username, user.email, password_hash)
        )
        conn.commit()
        conn.close()
        return {"status": "success", "message": "회원가입이 완료되었습니다."}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="회원가입에 실패했습니다. 다시 시도하세요.")

@app.post("/login")
async def login(request: LoginRequest):
    """로그인 엔드포인트"""
    
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT id, username, password FROM users WHERE username = ?", (request.username,))
    user_row = cur.fetchone()
    conn.close()
    
    if not user_row or not verify_password(user_row[2], request.password):
        raise HTTPException(status_code=401, detail="사용자명 또는 비밀번호가 잘못되었습니다.")
    
    # 세션 생성
    session_token = create_session_token()
    SESSIONS[session_token] = {
        "user_id": user_row[0],
        "username": user_row[1]
    }
    
    response = JSONResponse(
        {"status": "success", "message": f"{request.username}님 환영합니다!", "username": user_row[1]}
    )
    response.set_cookie(key="session_token", value=session_token, httponly=True, max_age=86400)  # 24시간
    return response

@app.post("/logout")
async def logout(session_token: str = Cookie(None)):
    """로그아웃 엔드포인트"""
    
    if session_token and session_token in SESSIONS:
        del SESSIONS[session_token]
    
    response = JSONResponse({"status": "success", "message": "로그아웃되었습니다."})
    response.delete_cookie("session_token")
    return response

@app.get("/user/check")
async def check_user(session_token: str = Cookie(None)):
    """현재 로그인된 사용자 정보 조회"""
    
    if not session_token or session_token not in SESSIONS:
        return {"logged_in": False, "username": None, "is_admin": False}
    
    user_info = SESSIONS[session_token]
    return {"logged_in": True, "username": user_info["username"], "is_admin": user_info["username"] == "system"}


# ===============================================
# 게시글 API (CUD)
# ===============================================
@app.post("/write")
async def create_post(post: Post, session_token: str = Cookie(None)):
    # 로그인 확인
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    # 공지 작성 권한 확인
    if post.is_notice and user["username"] != "system":
        raise HTTPException(status_code=403, detail="공지사항은 관리자만 작성할 수 있습니다.")

    # 1. 욕설 감지 및 점수/단계 계산 (마스킹은 읽을 때 동적으로 적용)
    #    우리는 원본 텍스트를 DB에 보관하고, 마스킹은 조회 시점에 적용합니다.
    _, swear_score, swear_level = censor_content(post.content, use_ml=True)

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. 데이터베이스 저장 (치환된 내용 + 욕설 점수/단계)
    cur.execute(
        "INSERT INTO posts (title, content, category, is_notice, created_at, author, views, swear_score, swear_level, raw_content) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (post.title, post.content, post.category, int(post.is_notice), current_time, user["username"], 0, swear_score, swear_level, post.content)
    )
    new_post_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"status": "success", "message": "게시글이 성공적으로 등록되었습니다.", "id": new_post_id}

# ... (다른 게시글 API들은 변경 없음) ...

@app.get("/posts")
def get_posts(category: str = None, session_token: str = Cookie(None)):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    
    # 현재 사용자가 관리자인지 확인
    user = get_current_user(session_token)
    is_admin = user and user["username"] == "system"
    
    # 댓글 수 카운트를 포함하도록 쿼리 수정, swear_score와 swear_level 추가
    base_query = """
        SELECT 
            p.id, 
            p.title, 
            p.is_notice, 
            strftime('%Y-%m-%d', p.created_at),
            COUNT(c.id),
            p.author,
            p.views,
            p.swear_score,
            p.swear_level
        FROM posts p
        LEFT JOIN comments c ON p.id = c.post_id
    """
    
    where_clause = ""
    params = []
    
    if category and category != "전체":
        where_clause = " WHERE p.category = ?"
        params.append(category)

    group_order_clause = " GROUP BY p.id ORDER BY p.is_notice DESC, p.id DESC"
    
    query = base_query + where_clause + group_order_clause
    
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    
    # 튜플을 리스트로 변환 (프론트엔드 호환성)
    # 관리자가 아니면 swear_score와 swear_level을 제거 (기본값으로 반환)
    # [id, title, is_notice, date, comment_count, author, views, swear_score, swear_level]
    posts_list = [
        [row[0], row[1], bool(row[2]), row[3], row[4], row[5], row[6], 
         (row[7] or 0.0) if is_admin else 0.0, 
         (row[8] or 'none') if is_admin else 'none'] 
        for row in rows
    ]
    return {"posts": posts_list}


@app.get("/post/{post_id}")
def get_post(post_id: int, session_token: str = Cookie(None)):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    # 조회수 증가
    cur.execute("UPDATE posts SET views = COALESCE(views,0) + 1 WHERE id = ?", (post_id,))
    conn.commit()

    cur.execute("SELECT id, title, content, raw_content, created_at, category, is_notice, author, views, swear_score, swear_level FROM posts WHERE id = ?", (post_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    
    # 현재 사용자가 관리자인지 확인
    user = get_current_user(session_token)
    is_admin = user and user["username"] == "system"
    
    # raw_content (index 3) contains the original unmasked text if present
    raw = row[3] if row[3] is not None else row[2]
    post = {
        "id": row[0],
        "title": row[1],
        "content": apply_dynamic_filtering(raw, row[9] or 0.0, row[10] or 'none'),
        "created_at": row[4],
        "category": row[5],
        "is_notice": bool(row[6]),
        "author": row[7],
        "views": row[8],
        "swear_score": (row[9] or 0.0) if is_admin else 0.0,
        "swear_level": (row[10] or 'none') if is_admin else 'none',
    }
    return post

@app.delete("/post/{post_id}")
def delete_post(post_id: int, session_token: str = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT author FROM posts WHERE id = ?", (post_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    author = row[0]
    if user["username"] != author and user["username"] != "system":
        conn.close()
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")

    cur.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    cur.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# ===============================================
# 댓글 API (CUD)
# ===============================================
@app.post("/comment")
async def create_comment(comment: Comment, session_token: str = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    # 1. 욕설 감지 및 점수/단계 계산 (마스킹은 조회 시점에 적용)
    _, swear_score, swear_level = censor_content(comment.content, use_ml=True)

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. 데이터베이스 저장 (치환된 내용 + 욕설 점수/단계)
    cur.execute("INSERT INTO comments (post_id, content, created_at, author, swear_score, swear_level, raw_content) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                (comment.post_id, comment.content, current_time, user["username"], swear_score, swear_level, comment.content))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/comments/{post_id}")
def get_comments(post_id: int, session_token: str = Cookie(None)):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    # id, content, raw_content, author, created_at, swear_score, swear_level 조회
    cur.execute("SELECT id, content, raw_content, author, created_at, swear_score, swear_level FROM comments WHERE post_id = ? ORDER BY id ASC", (post_id,))
    rows = cur.fetchall()
    conn.close()

    # 현재 사용자가 관리자인지 확인
    user = get_current_user(session_token)
    is_admin = user and user["username"] == "system"

    # 튜플을 리스트로 변환하고 동적 필터링 적용
    # 관리자가 아니면 swear_score와 swear_level을 숨기고 기본값으로 반환
    comments_list = [
        [
            row[0],
            apply_dynamic_filtering(row[2] if row[2] is not None else row[1], row[5] or 0.0, row[6] or 'none'),
            row[3],
            row[4],
            (row[5] or 0.0) if is_admin else 0.0,
            (row[6] or 'none') if is_admin else 'none'
        ]
        for row in rows
    ]
    return {"comments": comments_list}

@app.delete("/comment/{comment_id}")
def delete_comment(comment_id: int, session_token: str = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT author FROM comments WHERE id = ?", (comment_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")

    author = row[0]
    if user["username"] != author and user["username"] != "system":
        conn.close()
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")

    cur.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(BASE_DIR, "static", "pslw.png"))

if __name__ == "__main__":
    import uvicorn
    print("🚀 FastAPI 서버 시작: http://127.0.0.1:8000")
    print("📱 브라우저에서 http://127.0.0.1:8000 으로 접속하세요")
    uvicorn.run(app, host="127.0.0.1", port=8000)