import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="연령별 인구현황 대시보드", layout="wide")

DATA_PATH = "202606_202606_연령별인구현황_월간.csv"
AGE_LABELS = [str(i) for i in range(0, 100)] + ["100세 이상"]


@st.cache_data(show_spinner=True)
def load_data(path: str) -> pd.DataFrame:
    """행정안전부 연령별 인구현황(월간) CSV를 읽어 정리된 DataFrame으로 반환."""
    df = pd.read_csv(path, encoding="cp949", thousands=",")

    # 행정구역 컬럼에서 지역명과 행정코드 분리 (예: "서울특별시 종로구(1111000000)")
    region_raw = df["행정구역"].astype(str)
    codes = region_raw.str.extract(r"\((\d+)\)\s*$")[0]
    names = region_raw.str.replace(r"\s*\(\d+\)\s*$", "", regex=True).str.strip()
    df.insert(0, "행정코드", codes)
    df.insert(0, "지역명", names)

    # 지역 레벨(시도/시군구/읍면동) 추정: 공백으로 나뉜 토큰 수 기준
    def guess_level(name: str) -> str:
        tokens = name.split()
        if len(tokens) <= 1:
            return "시도"
        elif len(tokens) == 2:
            return "시군구"
        else:
            return "읍면동"

    df["지역레벨"] = df["지역명"].apply(guess_level)
    df["시도"] = df["지역명"].apply(lambda x: x.split()[0])

    # 지역명이 중복되는 경우(예: 세종특별자치시가 시도/시군구 레벨에 모두 등장)를 대비해
    # 화면 표시 및 내부 조회에 쓸 고유 표시명을 만든다.
    dup_mask = df["지역명"].duplicated(keep=False)
    df["표시명"] = df["지역명"]
    df.loc[dup_mask, "표시명"] = (
        df.loc[dup_mask, "지역명"] + " [코드:" + df.loc[dup_mask, "행정코드"].astype(str) + "]"
    )

    # 계/남/여 총인구수
    df = df.rename(columns={
        "2026년06월_계_총인구수": "총인구수_계",
        "2026년06월_남_총인구수": "총인구수_남",
        "2026년06월_여_총인구수": "총인구수_여",
    })

    return df


@st.cache_data(show_spinner=False)
def get_age_matrix(df: pd.DataFrame, gender: str) -> pd.DataFrame:
    """성별(계/남/여)에 대한 0~100세 이상 인구수 매트릭스를 반환. index = 표시명(고유)"""
    cols = [f"2026년06월_{gender}_{age}세" if age != "100세 이상" else f"2026년06월_{gender}_100세 이상"
            for age in AGE_LABELS]
    mat = df.set_index("표시명")[cols]
    mat.columns = AGE_LABELS
    return mat


df = load_data(DATA_PATH)
age_all = get_age_matrix(df, "계")
age_male = get_age_matrix(df, "남")
age_female = get_age_matrix(df, "여")

st.title("📊 연령별 인구현황 대시보드 (2026년 6월)")
st.caption("행정안전부 주민등록 연령별 인구현황 데이터를 기반으로 합니다.")

tab1, tab2 = st.tabs(["🏙️ 지역별 인구구조 살펴보기", "👯 인구구조 쌍둥이 지역 찾기"])

# ──────────────────────────────────────────────────────────────────────────
# TAB 1: 지역 선택 → 인구 피라미드 / 연령별 그래프
# ──────────────────────────────────────────────────────────────────────────
with tab1:
    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        sido_list = ["전체"] + sorted(df["시도"].unique().tolist())
        sido_sel = st.selectbox("시도 필터", sido_list, key="sido_filter_1")

    region_pool = df if sido_sel == "전체" else df[df["시도"] == sido_sel]
    region_names = region_pool["표시명"].tolist()

    with col_f2:
        region = st.selectbox(
            "지역 선택 (입력해서 검색 가능)",
            region_names,
            index=0,
            key="region_select_1",
        )

    row = df[df["표시명"] == region].iloc[0]
    total_pop = int(row["총인구수_계"])
    male_pop = int(row["총인구수_남"])
    female_pop = int(row["총인구수_여"])

    m1, m2, m3 = st.columns(3)
    m1.metric("총인구수", f"{total_pop:,} 명")
    m2.metric("남성", f"{male_pop:,} 명")
    m3.metric("여성", f"{female_pop:,} 명")

    st.divider()

    graph_type = st.radio(
        "그래프 유형", ["인구 피라미드", "연령별 인구 라인차트", "연령별 인구 영역차트"],
        horizontal=True,
    )

    male_vals = age_male.loc[region].values.astype(float)
    female_vals = age_female.loc[region].values.astype(float)
    total_vals = age_all.loc[region].values.astype(float)

    if graph_type == "인구 피라미드":
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=AGE_LABELS, x=-male_vals, name="남성", orientation="h",
            marker_color="#4C78A8",
            hovertemplate="연령: %{y}<br>남성: %{customdata:,}명<extra></extra>",
            customdata=male_vals,
        ))
        fig.add_trace(go.Bar(
            y=AGE_LABELS, x=female_vals, name="여성", orientation="h",
            marker_color="#F58518",
            hovertemplate="연령: %{y}<br>여성: %{x:,}명<extra></extra>",
        ))
        max_val = max(male_vals.max(), female_vals.max())
        fig.update_layout(
            title=f"{region} 인구 피라미드",
            barmode="relative",
            bargap=0.05,
            xaxis=dict(
                title="인구수",
                tickvals=np.linspace(-max_val, max_val, 9),
                ticktext=[f"{abs(int(v)):,}" for v in np.linspace(-max_val, max_val, 9)],
            ),
            yaxis=dict(title="연령", categoryorder="array", categoryarray=AGE_LABELS),
            height=900,
            hovermode="y unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    elif graph_type == "연령별 인구 라인차트":
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=AGE_LABELS, y=male_vals, mode="lines+markers", name="남성", line=dict(color="#4C78A8")))
        fig.add_trace(go.Scatter(x=AGE_LABELS, y=female_vals, mode="lines+markers", name="여성", line=dict(color="#F58518")))
        fig.add_trace(go.Scatter(x=AGE_LABELS, y=total_vals, mode="lines", name="전체", line=dict(color="gray", dash="dot")))
        fig.update_layout(
            title=f"{region} 연령별 인구 분포",
            xaxis_title="연령", yaxis_title="인구수",
            height=600, hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    else:  # 영역차트
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=AGE_LABELS, y=male_vals, mode="lines", name="남성", stackgroup="one", line=dict(color="#4C78A8")))
        fig.add_trace(go.Scatter(x=AGE_LABELS, y=female_vals, mode="lines", name="여성", stackgroup="one", line=dict(color="#F58518")))
        fig.update_layout(
            title=f"{region} 연령별 인구 누적 영역차트",
            xaxis_title="연령", yaxis_title="인구수",
            height=600, hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("원본 데이터 보기"):
        st.dataframe(row.to_frame().T)

# ──────────────────────────────────────────────────────────────────────────
# TAB 2: 인구구조 쌍둥이 지역 찾기
# ──────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown(
        "선택한 지역과 **연령별 인구 구성 비율**이 가장 비슷한 '쌍둥이 지역'을 찾아줍니다. "
        "(인구 규모가 아니라 연령대별 비율 구조를 비교합니다.)"
    )

    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        sido_sel2 = st.selectbox("시도 필터", ["전체"] + sorted(df["시도"].unique().tolist()), key="sido_filter_2")

    region_pool2 = df if sido_sel2 == "전체" else df[df["시도"] == sido_sel2]

    with col_f2:
        target_region = st.selectbox(
            "궁금한 지역 선택 (입력해서 검색 가능)",
            region_pool2["표시명"].tolist(),
            key="region_select_2",
        )

    col_opt1, col_opt2, col_opt3 = st.columns(3)
    with col_opt1:
        same_level_only = st.checkbox("같은 지역 단위끼리만 비교 (시도/시군구/읍면동)", value=True)
    with col_opt2:
        min_pop = st.number_input("최소 총인구수 (그 이하 지역 제외)", min_value=0, value=1000, step=500)
    with col_opt3:
        top_n = st.slider("상위 몇 개 지역을 보여줄까요?", 3, 20, 5)

    # 연령별 "비율" 매트릭스 계산 (지역별 총합으로 정규화)
    age_ratio = age_all.div(age_all.sum(axis=1), axis=0)

    candidates = df.copy()
    candidates = candidates[candidates["총인구수_계"] >= min_pop]
    if same_level_only:
        target_level = df.loc[df["표시명"] == target_region, "지역레벨"].values[0]
        candidates = candidates[candidates["지역레벨"] == target_level]
    candidates = candidates[candidates["표시명"] != target_region]

    target_vec = age_ratio.loc[target_region].values.astype(float)

    def cosine_sim(a, b):
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    results = []
    for name in candidates["표시명"]:
        vec = age_ratio.loc[name].values.astype(float)
        sim = cosine_sim(target_vec, vec)
        dist = float(np.linalg.norm(target_vec - vec))  # 유클리드 거리 (참고용)
        results.append((name, sim, dist))

    res_df = pd.DataFrame(results, columns=["지역명", "유사도(코사인)", "거리(유클리드)"])
    res_df = res_df.sort_values("유사도(코사인)", ascending=False).head(top_n)
    res_df = res_df.merge(
        df[["표시명", "총인구수_계", "지역레벨"]].rename(columns={"표시명": "지역명"}),
        on="지역명", how="left",
    )
    res_df["유사도(코사인)"] = (res_df["유사도(코사인)"] * 100).round(2)
    res_df = res_df.rename(columns={"유사도(코사인)": "유사도(%)", "총인구수_계": "총인구수"})
    res_df = res_df[["지역명", "유사도(%)", "거리(유클리드)", "총인구수", "지역레벨"]].reset_index(drop=True)

    st.subheader(f"🏆 '{target_region}'와(과) 가장 인구구조가 비슷한 지역 Top {top_n}")
    st.dataframe(res_df, use_container_width=True)

    if not res_df.empty:
        st.divider()
        st.subheader("연령 구조 비교 그래프")
        compare_targets = st.multiselect(
            "비교할 지역 선택 (기본: 1위 쌍둥이 지역)",
            res_df["지역명"].tolist(),
            default=[res_df["지역명"].iloc[0]],
        )

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=AGE_LABELS, y=age_ratio.loc[target_region].values * 100,
            mode="lines", name=f"{target_region} (기준)",
            line=dict(width=4, color="black"),
        ))
        palette = px.colors.qualitative.Set2
        for i, name in enumerate(compare_targets):
            fig.add_trace(go.Scatter(
                x=AGE_LABELS, y=age_ratio.loc[name].values * 100,
                mode="lines", name=name,
                line=dict(width=2, color=palette[i % len(palette)]),
            ))
        fig.update_layout(
            title="연령별 인구 비율(%) 비교",
            xaxis_title="연령", yaxis_title="비율 (%)",
            height=600, hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "※ '지역레벨'은 행정구역명 토큰 수로 추정한 값이라 세종특별자치시 등 일부 지역은 "
        "실제 행정 단위와 다르게 분류될 수 있습니다."
    )
