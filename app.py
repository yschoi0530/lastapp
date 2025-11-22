import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import uuid
import os
import bcrypt
import random
import numpy as np # 🚨 수정 1: NaT 체크를 위해 numpy 임포트

# ---------- 설정 ----------
st.set_page_config(page_title="머니모니", layout="wide")
st.title("머니모니 - 청소년 소비 습관 관리 앱")

USERS_FILE = "users.csv"
DEFAULT_MONTHLY_BUDGET = 200000 # 기본 예산 설정
PLAN_FILE_PREFIX = "_plan.txt" # 소비 계획 저장 파일 접미사
BUDGET_FILE_SUFFIX = "_budget.txt" # 월 예산 저장 파일 접미사

# 고정된 시작 날짜 (2025년 11월 17일 월요일)
START_DATE = datetime(2025, 11, 17)

# 카테고리 옵션
CATEGORY_OPTIONS = [
    "식비(간식/외식 포함)", "의류/패션/잡화", "미용(화장품 등)", "교통",
    "학습 자료", "문화 생활(친구모임/영화 등)", "취미용품/굿즈", "기타",
    "기부"
]

# 카테고리 매핑 (사용자 입력 단순화 반영)
CATEGORY_MAP = {
    "식비": "식비(간식/외식 포함)",
    "교통": "교통",
    "기타": "기타",
    "의류": "의류/패션/잡화",
    "학습 자료": "학습 자료",
    "문화 생활": "문화 생활(친구모임/영화 등)",
    "미용": "미용(화장품 등)",
    "의류/패션/잡화": "의류/패션/잡화"
} 

# ---------- 유틸 함수 ----------
def load_users():
    """사용자 정보(ID, 해시 비밀번호)를 로드합니다."""
    if os.path.exists(USERS_FILE):
        return pd.read_csv(USERS_FILE, dtype=str)
    else:
        return pd.DataFrame(columns=["username", "password_hash"])

def save_users(df):
    """사용자 정보를 저장합니다."""
    df.to_csv(USERS_FILE, index=False)

def hash_password(password):
    """비밀번호를 해시합니다."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    """비밀번호와 해시값을 비교하여 일치하는지 확인합니다."""
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

def load_data(username):
    """특정 사용자의 지출 기록을 로드합니다."""
    file = f"{username}_records.csv"
    
    if not os.path.exists(file):
        cols = ["id","날짜","시간","datetime_iso","대분류","세부항목","금액","계획됨","과시소비", "모방소비", "감정", "감정 이유"]
        return pd.DataFrame(columns=cols)

    df = pd.read_csv(file, dtype={"id": str})
    
    # 데이터 타입 및 호환성 처리
    if "datetime_iso" in df.columns:
        # 🚨 수정 2: errors='coerce'를 사용하여 잘못된 값은 NaT로 변환
        df["datetime_iso"] = pd.to_datetime(df["datetime_iso"], errors='coerce')
    
    if '모방소비' not in df.columns: df['모방소비'] = '아니오'
    if '감정 이유' not in df.columns: df['감정 이유'] = ''
        
    return df

def save_data(df, username):
    """특정 사용자의 지출 기록을 저장합니다."""
    df2 = df.copy()
    if "datetime_iso" in df2.columns:
        df2["datetime_iso"] = df2["datetime_iso"].astype(str)
    df2.to_csv(f"{username}_records.csv", index=False)
    
def load_plan(username):
    """특정 사용자의 소비 계획을 로드합니다. (이번 주 성찰, 다음 주 계획)"""
    file = f"{username}{PLAN_FILE_PREFIX}"
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
            reflection = lines[0].strip() if len(lines) > 0 else ""
            plan = lines[1].strip() if len(lines) > 1 else ""
            return reflection, plan
    return "", ""

def save_plan(username, reflection, plan):
    """특정 사용자의 소비 계획을 저장합니다."""
    file = f"{username}{PLAN_FILE_PREFIX}"
    with open(file, 'w', encoding='utf-8') as f:
        f.write(f"{reflection}\n{plan}")

def load_user_budget(username):
    """특정 사용자의 월 예산을 로드합니다. 파일이 없으면 기본값을 반환합니다."""
    file = f"{username}{BUDGET_FILE_SUFFIX}"
    if os.path.exists(file):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                return int(f.read().strip())
        except ValueError:
            return DEFAULT_MONTHLY_BUDGET
    return DEFAULT_MONTHLY_BUDGET

def save_user_budget(username, budget):
    """특정 사용자의 월 예산을 저장합니다."""
    file = f"{username}{BUDGET_FILE_SUFFIX}"
    with open(file, 'w', encoding='utf-8') as f:
        f.write(str(int(budget)))

def delete_user_files(username):
    """특정 사용자의 모든 관련 데이터 파일을 삭제합니다."""
    record_file = f"{username}_records.csv"
    plan_file = f"{username}{PLAN_FILE_PREFIX}"
    budget_file = f"{username}{BUDGET_FILE_SUFFIX}"
    
    if os.path.exists(record_file):
        os.remove(record_file)
    if os.path.exists(plan_file):
        os.remove(plan_file)
    if os.path.exists(budget_file):
        os.remove(budget_file)

def week_key(dt):
    """주차를 (년, 주) 튜플로 반환합니다. NaT는 (0, 0)으로 처리합니다."""
    # 🚨 수정 3: NaT 값 체크 및 처리
    if pd.isnull(dt) or not isinstance(dt, (datetime, pd.Timestamp)):
        return (0, 0)
        
    iso = dt.isocalendar()
    return (iso.year, iso.week)

# ---------- 요청받은 특정 데이터 생성 함수 (중복 완전 방지 버전) ----------

def create_specific_data(username):
    """요청받은 사용자별 특정 데이터를 생성하여 저장합니다."""

    # 날짜 계산: START_DATE 기준 (2025년 11월 17일 월요일)
    def get_datetime(day_offset, time_str):
        date_obj = START_DATE + timedelta(days=day_offset)
        hour, minute, second = map(int, time_str.split(':')) if ':' in time_str else (map(int, time_str.split(':') + ['00']))
        return date_obj.replace(hour=hour, minute=minute, second=second)

    # ... (기존 data_map 정의는 동일하게 유지) ...
    data_map = {
        "kim": [
            (0, '18:40:00', 3500, '식비', '음료수', False, '아니오', '아니오', '좋음', '맛있어서'),
            (0, '19:00:00', 1350, '교통', '버스비', True, '아니오', '아니오', '보통', ''),
            (1, '23:35:00', 900, '식비', '아이스크림', False, '아니오', '예', '', ''),
            (1, '19:30:00', 1350, '교통', '버스비', True, '아니오', '예', '', ''),
            (2, '18:28:00', 2500, '식비', '음료수', False, '아니오', '아니오', '좋음', '결명자차기 맛있었다!!'),
            (2, '21:50:00', 4150, '교통', '택시비', False, '아니오', '아니오', '나쁨', '안 나가도 될 돈 나감'),
            (3, '19:35:00', 3000, '기타', '교회 준비물', True, '아니오', '아니오', '', ''),
            (3, '21:00:00', 2000, '기타', '노트', False, '아니오', '아니오', '보통', ''),
            (3, '21:01:00', 5900, '의류/패션/잡화', '장갑', False, '아니오', '아니오', '좋음', '장갑 귀여움'),
            (4, '17:37:00', 6000, '학습 자료', '학술제 논문', True, '아니오', '예', '나쁨', '너무 오래됨'),
            (4, '19:43:00', 1800, '기타', '볼펜', False, '예', '아니오', '보통', ''),
            (5, '09:40:00', 4700, '교통', '택시비', False, '아니오', '예', '', ''),
            (5, '13:03:00', 15000, '의류/패션/잡화', '선크림', False, '아니오', '아니오', '', ''),
            (5, '15:40:00', 1350, '교통', '버스비', True, '아니오', '아니오', '보통', ''),
            (6, '07:40:00', 4700, '교통', '택시비', True, '아니오', '아니오', '', ''),
            (6, '12:31:00', 1500, '식비', '삼김', False, '아니오', '예', '', ''),
            (6, '17:32:00', 3500, '식비', '음료수', True, '아니오', '예', '보통', ''),
        ],

        "oh": [
            (0, '21:40:00', 2300, '식비', '아이스크림', False, '아니오', '예', '나쁨', '추워짐'),
            (0, '23:40:00', 36000, '학습 자료', '인강 정기결제', True, '아니오', '아니오', '나쁨', '취소 깜빡'),
            (1, '23:35:00', 1500, '식비', '카페 디저트', False, '아니오', '예', '좋음', '맛있음'),
            (1, '21:30:00', 6500, '교통', '택시비', True, '아니오', '아니오', '보통', ''),
            (2, '18:28:00', 900, '식비', '멘토스', False, '아니오', '아니오', '나쁨', '개노맛'),
            (2, '18:35:00', 4500, '식비', '카페 음료', True, '아니오', '아니오', '나쁨', '배부른데 먹음'),
            (3, '21:35:00', 4500, '교통', '택시비', True, '아니오', '아니오', '보통', ''),
            (3, '23:00:00', 12400, '식비', '아이스크림', False, '예', '아니오', '좋음', '쟁여둠'),
            (4, '17:37:00', 6000, '학습 자료', '학술제 논문', True, '아니오', '예', '나쁨', ''),
            (4, '19:20:00', 4400, '기타', '애플 클라우드', True, '예', '예', '나쁨', ''),
            (5, '13:20:00', 10000, '식비', '에너지음료', False, '아니오', '예', '좋음', '배송 기다림'),
            (5, '13:20:00', 24400, '의류/패션/잡화', '수딩젤', False, '아니오', '예', '좋음', ''),
            (5, '18:00:00', 1500, '식비', '토스트', False, '아니오', '아니오', '나쁨', '잘못 고름'),
            (6, '15:31:00', 1500, '식비', '젤리', False, '아니오', '예', '나쁨', ''),
            (6, '17:32:00', 3700, '식비', '음료수', True, '아니오', '예', '보통', ''),
        ],

        "choi": [
            (0, '08:42:00', 4000, '교통', '택시비', True, '아니오', '아니오', '보통', ''),
            (0, '11:46:00', 57700, '기타', '병원', True, '아니오', '아니오', '나쁨', '몸 관리 부족'),
            (0, '11:49:00', 4600, '기타', '병원', True, '아니오', '아니오', '나쁨', ''),
            (1, '23:05:00', 1000, '문화 생활', '웹툰', False, '아니오', '아니오', '나쁨', ''),
            (1, '23:35:00', 2000, '식비', '편의점', False, '아니오', '아니오', '좋음', ''),
            (2, '18:28:00', 12500, '식비', '배달', False, '아니오', '예', '보통', ''),
            (2, '19:32:00', 2700, '의류/패션/잡화', '올리브영', False, '예', '예', '좋음', ''),
            (3, '17:00:00', 3000, '식비', '편의점', False, '아니오', '아니오', '좋음', ''),
            (3, '17:42:00', 6700, '식비', '카페', False, '아니오', '예', '보통', ''),
            (4, '08:04:00', 3750, '식비', '마트', False, '아니오', '아니오', '나쁨', ''),
            (4, '23:35:00', 2000, '식비', '편의점', False, '아니오', '아니오', '좋음', ''),
            (5, '11:02:00', 1100, '기타', '애플 클라우드', True, '아니오', '아니오', '나쁨', ''),
            (5, '19:03:00', 3000, '문화 생활', '노래방', False, '아니오', '아니오', '좋음', ''),
            (6, '14:37:00', 3600, '식비', '카페', False, '예', '예', '좋음', ''),
            (6, '14:53:00', 2500, '식비', '마트', False, '아니오', '아니오', '보통', ''),
        ]
    }
    
    # 기존 기록 불러오기
    df_existing = load_data(username)

    # 기존 기록의 중복 기준 키셋 생성
    existing_dup_keys = set()
    if not df_existing.empty and "datetime_iso" in df_existing.columns:
        # datetime_iso를 문자열로 변환하여 중복 키를 생성하고 set에 저장
        # NaT가 아닌 유효한 값만 처리
        df_valid_dt = df_existing[pd.notna(df_existing['datetime_iso'])]
        existing_dup_keys = set(
            df_valid_dt.apply(
                lambda row: f"{row['datetime_iso'].strftime('%Y-%m-%d')}|{row['datetime_iso'].strftime('%H:%M:%S')}|{int(row['금액'])}|{row['세부항목']}",
                axis=1
            )
        )

    new_records = []

    # 새로운 기록 생성 및 중복 검사
    for (day_offset, time_str, amount, base_category, detail,
          is_planned, flashy, imitation, emotion, reason) in data_map.get(username, []):

        dt_iso = get_datetime(day_offset, time_str)
        # 새로운 기록의 중복 키 생성
        dup_key = f"{dt_iso.strftime('%Y-%m-%d')}|{dt_iso.strftime('%H:%M:%S')}|{int(amount)}|{detail}"

        # 🚨 중복 체크: 기존 키셋에 새로운 키가 없는 경우에만 추가
        if dup_key not in existing_dup_keys:
            new_records.append({
                "id": str(uuid.uuid4()),
                "날짜": dt_iso.strftime("%Y-%m-%d"),
                "시간": dt_iso.strftime("%H:%M:%S"),
                "datetime_iso": dt_iso,
                "대분류": CATEGORY_MAP.get(base_category, base_category),
                "세부항목": detail,
                "금액": float(amount),
                "계획됨": "예" if is_planned else "아니오",
                "과시소비": flashy,
                "모방소비": imitation,
                "감정": emotion,
                "감정 이유": reason,
            })
            existing_dup_keys.add(dup_key) # 즉시 키셋에 추가하여 이번 실행 중에도 중복 방지

    if new_records:
        df_new = pd.DataFrame(new_records)
        df_final = pd.concat([df_existing.drop(columns=["dup_key"], errors='ignore'), df_new], ignore_index=True)
        df_final.sort_values(by="datetime_iso", inplace=True)
        save_data(df_final, username)

    return len(new_records)


# ---------- 데모 유저 생성 ----------
def initialize_demo_users_and_data():
    """요청받은 사용자별 특정 데이터를 생성하여 저장합니다."""
    users_to_create = ["kim", "oh", "choi"]
    password = "test1234"
    hashed_pass = hash_password(password)

    # 데모 데이터를 다시 생성하려면 이 플래그를 제거해야 합니다.
    if "demo_data_initialized" in st.session_state:
        del st.session_state["demo_data_initialized"]

    demo_budgets = {"kim": 70000, "oh": 100000, "choi": 120000}

    users_df = load_users()

    for user in users_to_create:
        # 🚨 기존 파일 삭제로 완전 초기화
        delete_user_files(user)
        
        if user not in users_df["username"].values:
            new_row = pd.DataFrame([{"username": user, "password_hash": hashed_pass}])
            users_df = pd.concat([users_df, new_row], ignore_index=True)
            st.toast(f"사용자 '{user}' 등록 완료.")

    save_users(users_df)

    # 이 시점에서 create_specific_data는 파일에 기록합니다.
    for user in users_to_create:
        count = create_specific_data(user)
        save_user_budget(user, demo_budgets[user])
        st.toast(f"'{user}'의 데이터 {count}건 저장 완료")

    st.session_state["demo_data_initialized"] = True # 🚨 플래그 설정
    st.success("데모 계정 생성 완료! 로그인하세요.")


# ---------- 로그인 / 회원가입 / 데모 설정 (사이드바) ----------
users_df = load_users()
st.sidebar.header("로그인 / 회원가입")

if st.sidebar.button("🚨 데모 데이터 생성", help="kim, oh, choi 계정을 비밀번호 'test1234'로 생성하고 요청된 데이터와 예산을 주입합니다."):
    initialize_demo_users_and_data()

auth_mode = st.sidebar.radio("모드 선택", ["로그인", "회원가입"])

if auth_mode == "회원가입":
    st.sidebar.subheader("새 계정 만들기")
    new_user = st.sidebar.text_input("사용자 아이디", key="signup_user")
    new_pass = st.sidebar.text_input("비밀번호", type="password", key="signup_pass")
    if st.sidebar.button("회원가입", key="signup_btn"):
        if new_user in users_df["username"].values:
            st.sidebar.error("이미 존재하는 아이디입니다.")
        elif not new_user or not new_pass:
            st.sidebar.error("아이디와 비밀번호를 입력해주세요.")
        else:
            users_df = pd.concat([users_df, pd.DataFrame([{"username": new_user, "password_hash": hash_password(new_pass)}])], ignore_index=True)
            save_users(users_df)
            st.sidebar.success("회원가입 완료! 로그인 해주세요.")
elif auth_mode == "로그인":
    st.sidebar.subheader("로그인")
    login_user = st.sidebar.text_input("아이디", key="login_user")
    login_pass = st.sidebar.text_input("비밀번호", type="password", key="login_pass")
    login_btn = st.sidebar.button("로그인", key="login_btn")
    if login_btn:
        if login_user in users_df["username"].values:
            hashed = users_df.loc[users_df["username"] == login_user, "password_hash"].values[0]
            if check_password(login_pass, hashed):
                st.sidebar.success(f"{login_user}님 환영합니다!")
                st.session_state["user"] = login_user
                st.rerun()
            else:
                st.sidebar.error("비밀번호가 틀렸습니다.")
        else:
            st.sidebar.error("존재하지 않는 아이디입니다.")

if "user" in st.session_state:
    if st.sidebar.button("로그아웃"):
        del st.session_state["user"]
        if "monthly_budget" in st.session_state:
            del st.session_state["monthly_budget"]
        if "weekly_budget" in st.session_state:
            del st.session_state["weekly_budget"]
        st.rerun()

# ---------- 로그인 확인 및 앱 본문 시작 ----------
if "user" not in st.session_state:
    st.warning("로그인 후 이용 가능합니다.")
    st.markdown("---")
    st.stop()

username = st.session_state["user"]
df = load_data(username)

# 💰 글로벌: 월 예산 설정
st.subheader("💰 나의 예산 설정")

# --- BUDGET LOADING LOGIC ---
if "monthly_budget" not in st.session_state:
    # 1. Load from file (if exists), otherwise use default
    initial_budget = load_user_budget(username)
    # 2. Store in session state
    st.session_state["monthly_budget"] = initial_budget
    st.session_state["weekly_budget"] = initial_budget / 4
# ----------------------------


with st.form("budget_form", clear_on_submit=False):
    month_budget_input = st.number_input(
        "한 달 예산을 입력하세요 (원)",
        min_value=0,
        step=10000,
        value=st.session_state["monthly_budget"],
        key="month_budget_input"
    )

    budget_submitted = st.form_submit_button("월 예산 저장 및 주간 예산 계산")
    
    if budget_submitted:
        if month_budget_input <= 0:
            st.error("예산은 0원보다 커야 합니다.")
        else:
            # 3. Save to file AND session state on form submission
            st.session_state["monthly_budget"] = month_budget_input
            st.session_state["weekly_budget"] = month_budget_input / 4
            save_user_budget(username, month_budget_input) # 예산 저장
            st.success(
                f"월 예산 저장 완료! 주간 예산은 **{int(st.session_state['weekly_budget']):,}원** 입니다."
            )
st.markdown("---")
st.header(f"안녕하세요, {username}님의 머니모니입니다.")


# ----------------------
# 탭 정의
# ----------------------
tab1, tab2, tab3 = st.tabs(["💸 지출 & 감정 기록", "📊 대시보드 & 진단", "🎁 미션 & 보상"])


# ----------------------
# 1️⃣ 지출 & 감정 기록 탭 (tab1)
# ----------------------
with tab1:
    st.subheader("1. 나의 지출 기록하기")
    
    # 지출 기록 폼
    with st.form("spend_form", clear_on_submit=True):
        col1, col2 = st.columns([2,1])
        with col1:
            category = st.selectbox("지출 대분류", CATEGORY_OPTIONS)
            detail = st.text_input("세부 항목 (예: 버블티, 영화 티켓, 운동화 등)")
            amount = st.number_input("지출 금액 (원)", min_value=0, value=0)
        with col2:
            planned = st.radio("계획된 소비인가요?", ("예", "아니오"), horizontal=True)
            flashy = st.radio("과시소비 여부", ("아니오", "예"), horizontal=True)
            imitation = st.radio("모방 소비 여부", ("아니오", "예"), horizontal=True)
        
        submitted = st.form_submit_button("기록 저장")
        
        # 폼 제출 시 데이터 저장 및 과소비 체크
        if submitted and amount > 0:
            now = datetime.now()
            rec = {
                "id": str(uuid.uuid4()),
                "날짜": now.strftime("%Y-%m-%d"),
                "시간": now.strftime("%H:%M:%S"),
                "datetime_iso": now,
                "대분류": category,
                "세부항목": detail if detail else category, # 세부 항목이 없으면 대분류로 대체
                "금액": float(amount),
                "계획됨": planned,
                "과시소비": flashy,
                "모방소비": imitation,
                "감정": "",
                "감정 이유": "" # 새로 추가된 필드는 초기값 비워둠
            }
            
            # DataFrame 업데이트 및 저장
            df_updated = pd.concat([df, pd.DataFrame([rec])], ignore_index=True)
            save_data(df_updated, username)
            
            st.success(f"기록 저장 완료: {category} / {rec['세부항목']} / {int(amount):,}원")
            
            # 🔥 주간 예산 기반 과소비 체크
            weekly_budget = st.session_state.get("weekly_budget", 0)
            
            if weekly_budget > 0:
                # 당일 지출 합계 계산 (저장된 df_updated 사용)
                today_date_str = now.strftime("%Y-%m-%d")
                df_updated["datetime_iso"] = pd.to_datetime(df_updated["datetime_iso"]) # 비교를 위해 타입 변환
                day_total = df_updated[df_updated["날짜"] == today_date_str]["금액"].sum()
                
                # 하루 허용 금액을 주간 예산의 30%로 설정 (임시 기준)
                daily_overspend_limit = weekly_budget * 0.3 
                
                if day_total > daily_overspend_limit:
                    st.error(f"⚠️ **과소비 발생!** 오늘 **{int(day_total):,}원**을 사용했어요.")
                    st.warning(f"하루 허용 금액은 **{int(daily_overspend_limit):,}원** 입니다. (주간 예산의 30%)")

            st.rerun() # 변경된 데이터로 화면 새로고침

    st.markdown("---")
    st.subheader("최근 기록")
    df = load_data(username) # 저장 후 데이터 다시 로드
    if not df.empty:
        # '감정 이유' 컬럼을 추가하여 표시
        display_cols = ['날짜', '시간', '대분류', '세부항목', '금액', '계획됨', '과시소비', '모방소비', '감정', '감정 이유'] 
        # 최신 기록 10건만 표시
        st.dataframe(df.sort_values("datetime_iso", ascending=False)[display_cols].head(10)) 
    else:
        st.write("기록이 없습니다.")
    
    st.markdown("---")

    # 2️⃣ 소비 감정 기록 (30분 대기 시간)
    st.subheader("2. 소비 후 감정 기록")
    st.caption("소비 후 30분 뒤부터 해당 지출에 대한 감정을 기록할 수 있어요.")
    
    now = datetime.now()
    # 지출 후 30분 이상 경과했고 감정 기록이 없는 항목만 필터링
    # NaT 값은 비교가 불가능하므로 제외 (pd.notna로 유효한 값만 포함)
    df_pending = df[pd.notna(df["datetime_iso"]) & 
                    (df["감정"].isnull() | (df["감정"] == "")) & 
                    (df["datetime_iso"] <= now - timedelta(minutes=30))]
    
    if df_pending.empty:
        st.info("감정 입력 가능한 항목이 없습니다.")
    else:
        st.warning(f"총 {len(df_pending)}건의 감정 기록이 필요합니다. 마음을 들여다봐요!")
        for idx, row in df_pending.iterrows():
            with st.expander(f"💰 {row['날짜']} {row['시간']} | {row['대분류']} / {row['세부항목']} • {int(row['금액']):,}원"):
                # 감정 선택
                emo_choice = st.radio(f"이 소비에 대한 당신의 감정은? (ID {row['id'][:4]}...)", 
                                     ("좋음", "보통", "나쁨"), 
                                     key=f"emo_radio_{row['id']}")
                
                # 감정 이유 입력 필드 추가
                reason_input = st.text_area(
                    "왜 이러한 감정이 들었는지 자세히 적어보세요.",
                    value=row.get('감정 이유', ''), # 기존 값이 있으면 불러오기
                    key=f"reason_input_{row['id']}",
                    height=50
                )
                
                if st.button("감정 저장 및 반영", key=f"saveemo_btn_{row['id']}"):
                    # 감정 및 감정 이유 모두 저장
                    df.loc[df["id"] == row["id"], "감정"] = emo_choice
                    df.loc[df["id"] == row["id"], "감정 이유"] = reason_input
                    save_data(df, username)
                    st.toast("✅ 감정 기록이 저장되었습니다. 화면을 새로고침합니다.")
                    st.rerun()


# ----------------------
# 2️⃣ 대시보드 & 진단 탭 (tab2)
# ----------------------
with tab2:
    st.header("📊 나의 소비 분석 대시보드")
    
    if df.empty:
        st.info("먼저 '지출 & 감정 기록' 탭에서 지출 기록을 시작해주세요.")
    else:
        # 3️⃣ 개인 대시보드
        st.subheader("3. 주간 소비 현황")
        
        # 주차 계산을 위한 기본 변수 설정
        df["year_week"] = df["datetime_iso"].apply(lambda x: week_key(x))
        
        # 🚨 수정 4-1: NaT로 인해 (0, 0)으로 설정된 행을 분석에서 제외
        df_cleaned = df[df["year_week"] != (0, 0)].copy() 
        
        if df_cleaned.empty:
            st.info("유효한 날짜가 포함된 기록이 없어 주간 분석을 할 수 없습니다.")
        else:
            # pandas Timestamp 대신 datetime.now() 사용
            today = datetime.now() 
            cur_week = week_key(today)
            weekly_budget = st.session_state["weekly_budget"]
            
            # 🚨 수정 4-2: weeks 리스트도 df_cleaned를 기반으로 생성
            weeks = sorted(df_cleaned["year_week"].unique(), reverse=True)
            
            if weeks:
                sel = st.selectbox("분석 주차 선택", options=weeks, format_func=lambda x: f"{x[0]}년 {x[1]}주차", key="dashboard_week_select")
                df_week = df_cleaned[df_cleaned["year_week"]==sel] # df_cleaned 사용
                
                # 주간 총 지출
                total_spent_week = df_week['금액'].sum()
                
                st.metric("설정된 주간 예산", f"{int(weekly_budget):,}원")
                # 예산 대비 사용률 계산 시 weekly_budget이 0이 아닌지 확인
                usage_percent = (total_spent_week / weekly_budget * 100) if weekly_budget > 0 else 0
                st.metric("선택 주차 총 지출", f"{int(total_spent_week):,}원", 
                          delta_color="inverse", 
                          delta=f"예산 대비 {usage_percent:.1f}% 사용")
                
                # 주간 카테고리별 지출
                category_spending = df_week.groupby('대분류')['금액'].sum().sort_values(ascending=False)
                st.write("---")
                st.markdown("##### 카테고리별 지출 분포")
                st.bar_chart(category_spending)
                st.dataframe(category_spending.to_frame(name="금액"))

                # 🚨 개선된 기능: 일별 지출 추이 (Line Chart)
                st.markdown("---")
                st.markdown("##### 📈 일별 지출 추이")
                
                # 날짜별 지출 합계 계산
                daily_spending = df_week.groupby('날짜')['금액'].sum().reset_index()
                daily_spending.rename(columns={'금액': '일별 총 지출'}, inplace=True)
                
                # 날짜를 인덱스로 설정하여 Streamlit 차트가 인식하도록 준비
                daily_spending['날짜'] = pd.to_datetime(daily_spending['날짜'])
                daily_spending.set_index('날짜', inplace=True)
                
                st.line_chart(daily_spending)
                st.dataframe(daily_spending)

            st.markdown("---")
            
            # 🚨 NEW FEATURE: 가장 큰 소비 카테고리 경고
            df_current_week_warning = df_cleaned[df_cleaned["year_week"] == cur_week] # df_cleaned 사용
            
            if not df_current_week_warning.empty:
                # 카테고리별 지출 합계 계산
                category_sums = df_current_week_warning.groupby('대분류')['금액'].sum()
                
                if not category_sums.empty:
                    highest_category = category_sums.idxmax()
                    
                    # 경고 메시지 출력
                    st.error(
                        f"🚨 **주간 소비 경고!** 현재까지 **{highest_category}**에 가장 많은 소비를 하고 있어요!! 자제하세요!!"
                    )

            # 4️⃣ 나의 소비 돌아보기 (주간 진단)
            st.subheader("4. 나의 주간 소비 진단")
            
            prev_week_dt = today - timedelta(days=7) # 지난 주 날짜 계산
            prev_week = week_key(prev_week_dt)

            def week_stats(df_all, yw, budget):
                """주간 통계를 계산합니다."""
                # df_all은 이미 year_week 컬럼으로 필터링 가능하도록 준비됨
                dfw = df_all[df_all["year_week"]==yw].copy()
                
                total_amount = dfw["금액"].sum() if not dfw.empty else 0
                
                # 예산이 0보다 커야 초과 여부를 판단
                budget_status = "🚨 초과" if total_amount > budget and budget > 0 else "✅ 적정" 
                
                impulse_count = dfw[dfw["계획됨"]=="아니오"].shape[0] if not dfw.empty else 0
                flashy_count = dfw[dfw["과시소비"]=="예"].shape[0] if not dfw.empty else 0
                imitation_count = dfw[dfw["모방소비"]=="예"].shape[0] if not dfw.empty else 0
                
                emo_mode = None
                if not dfw.empty:
                    # 감정 기록이 있는 데이터만 필터링
                    df_emotion = dfw[dfw["감정"].isin(["좋음", "보통", "나쁨"])]
                    if not df_emotion.empty:
                        mode_series = df_emotion["감정"].mode()
                        if not mode_series.empty:
                            emo_mode = mode_series.iloc[0]

                return {
                    "총 지출": int(total_amount),
                    "예산 초과 여부": budget_status,
                    "충동 구매 횟수": impulse_count,
                    "과시 소비 횟수": flashy_count,
                    "모방 소비 횟수": imitation_count, 
                    "가장 많은 소비 감정": emo_mode if emo_mode else "기록 부족"
                }

            # 🚨 수정 4-3: week_stats 호출 시 df_cleaned를 인자로 전달
            cur_stats = week_stats(df_cleaned, cur_week, weekly_budget)
            prev_stats = week_stats(df_cleaned, prev_week, weekly_budget)

            st.markdown(f"##### ✨ 이번 주 ({cur_week[0]}년 {cur_week[1]}주차) 진단 결과")
            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            
            # 델타 계산 및 표시
            delta_impulse = cur_stats['충동 구매 횟수'] - prev_stats['충동 구매 횟수']
            delta_flashy = cur_stats['과시 소비 횟수'] - prev_stats['과시 소비 횟수']
            delta_imitation = cur_stats['모방 소비 횟수'] - prev_stats['모방 소비 횟수']

            col_c1.metric("총 지출", f"{cur_stats['총 지출']:,}원", delta=f"{cur_stats['예산 초과 여부']}")
            col_c2.metric("충동 구매", f"{cur_stats['충동 구매 횟수']}건", delta=f"{delta_impulse}건 (지난 주 대비)", delta_color="inverse")
            col_c3.metric("과시 소비", f"{cur_stats['과시 소비 횟수']}건", delta=f"{delta_flashy}건 (지난 주 대비)", delta_color="inverse")
            col_c4.metric("모방 소비", f"{cur_stats['모방 소비 횟수']}건", delta=f"{delta_imitation}건 (지난 주 대비)", delta_color="inverse")

            st.info(f"이번 주 소비 시 가장 자주 느낀 감정은 **{cur_stats['가장 많은 소비 감정']}** 이에요. 감정 기록과 지출 내역을 비교해보세요!")
            
            # 5️⃣ 소비 계획 세우기
            st.markdown("---")
            st.subheader("5. 📅 소비 계획 및 성찰")

            # 기존 계획 로드
            current_reflection, current_plan = load_plan(username)

            with st.form("spending_plan_form", clear_on_submit=False):
                st.markdown("##### 이번 주 소비 성찰 (반성/만족)")
                reflection_input = st.text_area(
                    "이번주의 소비는... (직접 입력)",
                    value=current_reflection,
                    height=100,
                    key="reflection_input"
                )

                st.markdown("##### 다음 주 소비 계획 (목표/실천 항목)")
                plan_input = st.text_area(
                    "다음주의 소비는... (직접 입력)",
                    value=current_plan,
                    height=100,
                    key="plan_input"
                )
                
                plan_submitted = st.form_submit_button("성찰 및 계획 저장")

                if plan_submitted:
                    save_plan(username, reflection_input, plan_input)
                    st.success("소비 성찰 및 다음 주 계획이 저장되었습니다.")
                    st.rerun()


# ----------------------
# 3️⃣ 미션 & 보상 탭 (tab3)
# ----------------------
with tab3:
    st.header("🎁 미션 & 보상")
    st.markdown("건전한 소비 습관을 위한 미션을 달성하고 뱃지를 모아봐요!")

    if df.empty:
        st.info("지출 기록을 시작하면 뱃지 현황을 확인할 수 있어요.")
    else:
        # 뱃지 조건 리스트
        badge_list = [
            {"name": "첫 기록", "condition": lambda df: len(df) >= 1, "target": 1, "desc": "첫 지출 기록 달성"},
            {"name": "꾸준한 기록", "condition": lambda df: len(df) >= 7, "target": 7, "desc": "7건 이상 기록 달성"},
            {"name": "감정 성찰왕", "condition": lambda df: df["감정"].isin(["좋음", "보통", "나쁨"]).sum() >= 10, "target": 10, "desc": "10건 이상의 감정 기록 완료"},
            {"name": "계획 부자", "condition": lambda df: df[df["계획됨"] == "예"].shape[0] >= 15, "target": 15, "desc": "계획된 소비 15건 달성"},
            {"name": "절약 영웅", "condition": lambda df: df[(df["계획됨"] == "예") & (df["과시소비"] == "아니오")].shape[0] >= 20, "target": 20, "desc": "합리적 소비 20건 달성"}
        ]
        
        st.markdown("##### 🏆 나의 뱃지 현황")
        cols = st.columns(len(badge_list))
        
        for i, badge in enumerate(badge_list):
            current_count = 0
            
            # 조건에 따른 현재 카운트 계산
            if badge['name'] == "첫 기록" or badge['name'] == "꾸준한 기록":
                current_count = len(df)
            elif badge['name'] == "감정 성찰왕":
                # 감정 필드에서 유효한 값의 개수를 정확히 세도록 수정
                current_count = df[df["감정"].isin(["좋음", "보통", "나쁨"])].shape[0]
            elif badge['name'] == "계획 부자":
                current_count = df[df["계획됨"] == "예"].shape[0]
            elif badge['name'] == "절약 영웅":
                current_count = df[(df["계획됨"] == "예") & (df["과시소비"] == "아니오")].shape[0]
            
            earned = current_count >= badge['target']
            
            status_text = "✅ 획득 완료" if earned else f"❌ 미획득 ({current_count}/{badge['target']}회)"
            status_color = "green" if earned else "red"

            badge_icon = "✨" if earned else "🔒" 
            
            with cols[i]:
                st.markdown(f"**{badge_icon} {badge['name']}**", unsafe_allow_html=True)
                st.caption(f"_{badge['desc']}_")
                st.markdown(f"**<span style='color:{status_color}; font-weight:bold;'>{status_text}</span>**", unsafe_allow_html=True)
