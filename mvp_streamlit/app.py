"""
app.py — Streamlit メインアプリ
UX改修版・3C縦積みレイアウト ＋ PDF添付機能 ＋ UIプロフェッショナル化 ＋ 堅牢化
余白調整版（空スペース除去）
"""

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from retrieval.vector_store import search
from retrieval.graph_search import build_graph, build_context, get_neighbors

try:
    from llm.analyzer import analyze
    ANALYZER_AVAILABLE = True
except ValueError as e:
    ANALYZER_AVAILABLE = False
    ANALYZER_ERROR = str(e)
except ImportError:
    ANALYZER_AVAILABLE = False
    ANALYZER_ERROR = "analyzerモジュールが見つかりません。"


st.set_page_config(
    page_title="PROJECT ZERO — 新規事業判断支援",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CUSTOM_CSS = """
<style>
/* ===== 全体背景 ===== */
html, body, [data-testid="stAppViewContainer"], .stApp {
  background: #F8FAFC !important;
  color: #1E2A4A !important;
}

/* ===== ページ全体の余白を削減 ===== */
.block-container {
  padding-top: 0.7rem !important;
  padding-bottom: 1rem !important;
  padding-left: 1.5rem !important;
  padding-right: 1.5rem !important;
}

section.main > div {
  padding-top: 0 !important;
}

.element-container {
  margin-bottom: 0.25rem !important;
}

div[data-testid="stVerticalBlock"] > div:empty {
  display: none !important;
}

/* デフォルト文字色 */
h1, h2, h3, h4, h5, h6,
p, li, span, label, div,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span,
[data-testid="stWidgetLabel"],
[data-testid="stCaptionContainer"] {
  color: #111827 !important;
}

/* ===== フォーム自体をカード化 ===== */
[data-testid="stForm"] {
  background: #FFFFFF !important;
  border-radius: 18px !important;
  padding: 20px 20px 16px 20px !important;
  margin-top: 0.5rem !important;
  margin-bottom: 0.75rem !important;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08) !important;
  border: 1px solid #E5E7EB !important;
}

/* ===== 入力欄 ===== */
[data-testid="stForm"] input,
[data-testid="stForm"] textarea,
[data-testid="stForm"] [data-baseweb="input"] input,
[data-testid="stForm"] [data-baseweb="textarea"] textarea {
  background-color: #FFFFFF !important;
  color: #111827 !important;
  border: 1px solid #D1D5DB !important;
  border-radius: 10px !important;
}

[data-testid="stForm"] [data-baseweb="input"],
[data-testid="stForm"] [data-baseweb="textarea"] {
  background-color: #FFFFFF !important;
  border-radius: 10px !important;
}

[data-testid="stForm"] input::placeholder,
[data-testid="stForm"] textarea::placeholder {
  color: #6B7280 !important;
  opacity: 1 !important;
}

textarea {
  min-height: 120px !important;
}

/* ===== file_uploader ===== */
[data-testid="stForm"] [data-testid="stFileUploader"] {
  color: #111827 !important;
  margin-bottom: 0.25rem !important;
}

[data-testid="stForm"] [data-testid="stFileUploaderDropzone"] {
  background: #F9FAFB !important;
  border: 1px solid #D1D5DB !important;
  border-radius: 12px !important;
  padding-top: 0.75rem !important;
  padding-bottom: 0.75rem !important;
}

[data-testid="stForm"] [data-testid="stFileUploaderDropzone"] * {
  color: #111827 !important;
}

[data-testid="stForm"] [data-testid="stFileUploaderDropzone"] button,
[data-testid="stForm"] [data-testid="stBaseButton-secondary"] {
  background: #FFFFFF !important;
  color: #111827 !important;
  border: 1px solid #C7C9D1 !important;
  border-radius: 8px !important;
}

/* ===== ボタン：緑地＋白文字 ===== */
.stButton > button,
[data-testid="stFormSubmitButton"] button {
  background-color: #16A34A !important;
  color: #FFFFFF !important;
  border-radius: 10px;
  border: none;
  font-weight: 700;
  padding: 0.65rem 1.2rem;
}

.stButton > button:hover,
[data-testid="stFormSubmitButton"] button:hover {
  background-color: #15803D !important;
  color: #FFFFFF !important;
}

/* ===== アラート ===== */
[data-testid="stAlert"] {
  border-radius: 10px;
  margin-top: 0.35rem !important;
  margin-bottom: 0.5rem !important;
}

[data-testid="stInfo"] *,
[data-testid="stSuccess"] *,
[data-testid="stWarning"] *,
[data-testid="stError"] * {
  color: #111827 !important;
}

/* ===== 結果ブロック ===== */
.result-card {
  background: #FFFFFF !important;
  border-radius: 18px;
  padding: 20px 20px 16px 20px;
  margin-top: 0.5rem;
  margin-bottom: 0.75rem;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  border: 1px solid #E5E7EB;
}

.result-card * {
  color: #111827 !important;
}

.result-card [data-testid="stExpander"] {
  border: 1px solid #E5E7EB !important;
  border-radius: 12px !important;
  background: #FFFFFF !important;
  margin-top: 0.5rem !important;
  margin-bottom: 0.5rem !important;
}

.result-card [data-testid="stExpander"] summary,
.result-card [data-testid="stExpander"] * {
  color: #111827 !important;
}

.result-card [data-testid="stTabs"] {
  margin-top: 0.25rem !important;
}

.result-card [data-testid="stTabs"] button {
  color: #111827 !important;
}

.result-card [data-testid="stTabs"] button[aria-selected="true"] {
  color: #2563EB !important;
  font-weight: 700;
}

.result-card .stMetric {
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  padding: 12px;
}

.result-card [data-testid="stMetricLabel"],
.result-card [data-testid="stMetricValue"] {
  color: #111827 !important;
}

.result-card [data-testid="stAlert"] {
  background: #F9FAFB !important;
  border: 1px solid #E5E7EB !important;
}

/* 区切り線・余白削減 */
hr {
  border-color: #E5E7EB !important;
  margin-top: 0.75rem !important;
  margin-bottom: 0.75rem !important;
}

[data-testid="stVerticalBlock"] {
  gap: 0.35rem !important;
}

/* 3軸評価の記号サイズを揃える */
.result-card [data-testid="stMetricValue"] {
  font-size: 2.2rem !important;
  line-height: 1.2 !important;
  font-weight: 700 !important;
}

/* ===== ① 上部ヘッダーバー（Deploy等） ===== */
[data-testid="stHeader"],
[data-testid="stHeader"] *,
[data-testid="stToolbar"],
[data-testid="stToolbar"] *,
header[data-testid="stHeader"],
.stToolbar,
.stToolbar * {
  background-color: #FFFFFF !important;
  color: #111827 !important;
}

[data-testid="stHeader"] button,
[data-testid="stToolbar"] button {
  color: #111827 !important;
  background: transparent !important;
}

[data-testid="stHeader"] button:hover,
[data-testid="stToolbar"] button:hover {
  background: #F3F4F6 !important;
  color: #111827 !important;
}

/* ===== ② text_input 入力完了後も含めた黒背景・白文字を防ぐ ===== */
[data-baseweb="input"],
[data-baseweb="base-input"],
[data-baseweb="textarea"],
[data-baseweb="input"] > div,
[data-baseweb="base-input"] > div,
[data-baseweb="textarea"] > div,
[data-baseweb="input"]:focus-within,
[data-baseweb="base-input"]:focus-within,
[data-baseweb="textarea"]:focus-within,
[data-baseweb="input"]:not(:focus-within),
[data-baseweb="base-input"]:not(:focus-within),
[data-baseweb="textarea"]:not(:focus-within) {
  background-color: #FFFFFF !important;
  color: #111827 !important;
}

[data-baseweb="input"] input,
[data-baseweb="base-input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="input"] input:focus,
[data-baseweb="base-input"] input:focus,
[data-baseweb="textarea"] textarea:focus,
[data-baseweb="input"] input:not(:focus),
[data-baseweb="base-input"] input:not(:focus),
[data-baseweb="textarea"] textarea:not(:focus) {
  background-color: #FFFFFF !important;
  color: #111827 !important;
  caret-color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}

/* autofill時のブラウザ上書きを防ぐ */
[data-baseweb="input"] input:-webkit-autofill,
[data-baseweb="base-input"] input:-webkit-autofill {
  -webkit-box-shadow: 0 0 0 1000px #FFFFFF inset !important;
  -webkit-text-fill-color: #111827 !important;
}

/* ===== placeholder（例：）をグレーに ===== */
input::placeholder,
textarea::placeholder {
  color: #9CA3AF !important;
  -webkit-text-fill-color: #9CA3AF !important;
  opacity: 1 !important;
}

/* ===== ④ expander トグルのホバー・通常時の黒背景を防ぐ ===== */
[data-testid="stExpander"],
[data-testid="stExpander"] > details,
[data-testid="stExpander"] > details > summary {
  background-color: #FFFFFF !important;
  color: #111827 !important;
}

[data-testid="stExpander"] > details > summary:hover {
  background-color: #F3F4F6 !important;
  color: #111827 !important;
}

[data-testid="stExpander"] > details[open] > summary {
  background-color: #FFFFFF !important;
  color: #111827 !important;
}

[data-testid="stExpander"] > details > summary * {
  color: #111827 !important;
}

[data-testid="stExpander"] > details > summary:hover * {
  color: #111827 !important;
}

</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


col_left, col_center, col_right = st.columns([1, 3, 1])
with col_center:
    st.image("factory.png", use_container_width=True)

if not ANALYZER_AVAILABLE:
    st.error(f"設定エラー: {ANALYZER_ERROR}")
    st.info(".env ファイルに OPENAI_API_KEY を設定するか、モジュールパスを確認してください。")
    st.stop()


@st.cache_resource
def get_graph():
    return build_graph()


def render_graph(highlighted_ids: set):
    G = get_graph()
    net = Network(height="500px", width="100%", bgcolor="#FFFFFF", font_color="#111827")

    type_colors = {
        "technology": "#22C55E",
        "person": "#3B82F6",
        "market": "#F59E0B",
        "past_project": "#A855F7",
    }

    for node_id, attrs in G.nodes(data=True):
        is_highlighted = node_id in highlighted_ids
        base_color = type_colors.get(attrs.get("type", ""), "#9CA3AF")
        net.add_node(
            node_id,
            label=attrs.get("label", node_id),
            color={
                "background": "#FDE68A" if is_highlighted else base_color,
                "border": "#F97316" if is_highlighted else base_color,
            },
            size=25 if is_highlighted else 15,
            title=f"{attrs.get('label', node_id)} ({attrs.get('type', '')})",
        )

    for src, tgt, attrs in G.edges(data=True):
        net.add_edge(src, tgt, title=attrs.get("relation", ""), color="#D1D5DB")

    html = net.generate_html()
    components.html(html, height=520)


st.markdown("### 💡 ビジネスアイデアの入力")

with st.form("idea_form"):
    st.markdown(
        '<p><strong>📁 既存の企画書・関連資料をアップロード（任意）</strong></p>',
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader(
        "PDFファイルを添付",
        type=["pdf"],
    )

    if uploaded_file is not None:
        st.success(f"📄 『{uploaded_file.name}』 を読み込みました。AIが文脈として考慮します。")

    col_input1, col_input2 = st.columns(2)
    with col_input1:
        target_market = st.text_input(
            "ターゲット市場 / 想定顧客",
            placeholder="例：欧州の大規模農業法人",
        )
    with col_input2:
        assets = st.text_input(
            "活用したい自社アセット・コア技術",
            placeholder='例：100%植物由来ポリマー「Green Planet」',
        )

    idea_detail = st.text_area(
        "提供価値・事業アイデアの詳細",
        placeholder="例：環境規制強化を背景に、農業用マルチフィルムとして展開。haあたり300ユーロの廃棄コストを削減し...",
    )

    run_button = st.form_submit_button("投資判断AIによる分析スタート", type="primary")


theme = f"【想定顧客/市場】{target_market}\n【活用アセット】{assets}\n【アイデア概要】{idea_detail}"


if run_button:
    if not idea_detail:
        st.warning("⚠️ 「提供価値・事業アイデアの詳細」は必ず入力してください。")
        st.stop()

    with st.status("🧠 AIが多角的に分析・評価中...", expanded=True) as status:
        if uploaded_file is not None:
            st.write("📑 添付されたPDF資料の内容を解析・抽出中...")

        st.write("🔍 社内データ・過去の失敗プロジェクトを検索中...")
        G = get_graph()
        vector_results = search(theme, n=5)

        st.write("📊 外部環境・社内資産・組織体制の文脈を構築中...")
        context = build_context(vector_results, graph=G)

        st.write("⚖️ 投資判断と3C分析を生成中（数秒かかります）...")
        results = analyze(theme, context, search_results=vector_results)

        status.update(label="✅ 分析完了！", state="complete", expanded=False)

    stage1 = results.get("stage1", {})
    stage2 = results.get("stage2", {})

    with st.container():
        st.markdown('<div class="result-card">', unsafe_allow_html=True)

        st.header("🎯 エグゼクティブ・サマリー（事業化 Go/No-Go 判定）")
        st.caption(
            "※本AI判定は、市場性・技術適合性・組織体制の3軸に基づき、初期投資の妥当性を評価したものです。"
        )

        summary_text = stage2.get(
            "approver_summary", "サマリー情報が生成されませんでした。"
        )
        st.info(summary_text, icon="📢")

        st.subheader("3軸評価と根拠詳細")

        ext_data = stage1.get("external", {})
        int_data = stage1.get("internal", {})
        org_data = stage1.get("org", {})

        with st.container():
            c_score, c_reason = st.columns([1, 4])
            with c_score:
                st.metric("🌍 外部環境", ext_data.get("score", "N/A"))
            with c_reason:
                st.markdown("**💡 評価根拠**")
                st.write(ext_data.get("reason", "評価根拠がありません。"))
        st.divider()

        with st.container():
            c_score, c_reason = st.columns([1, 4])
            with c_score:
                st.metric("🏢 社内適合", int_data.get("score", "N/A"))
            with c_reason:
                st.markdown("**💡 評価根拠**")
                st.write(int_data.get("reason", "評価根拠がありません。"))
        st.divider()

        with st.container():
            c_score, c_reason = st.columns([1, 4])
            with c_score:
                st.metric("🤝 組織体制", org_data.get("score", "N/A"))
            with c_reason:
                st.markdown("**💡 評価根拠**")
                st.write(org_data.get("reason", "評価根拠がありません。"))

        tab_proposal, tab_3c, tab_graph = st.tabs(
            ["💡 事業提案・アクション", "📊 3C分析", "🌐 関連ノードグラフ"]
        )

        with tab_proposal:
            st.subheader("AIからの提案")
            proposals = stage2.get("proposals", [])
            if proposals:
                for i, proposal in enumerate(proposals):
                    p_title = proposal.get("title", "無題の提案")

                    with st.expander(f"提案 {i+1}： {p_title}", expanded=(i == 0)):
                        st.write(proposal.get("summary", ""))

                        c1, c2 = st.columns(2)
                        with c1:
                            st.metric("タイミング評価", proposal.get("timing_score", "-"))
                            st.caption(proposal.get("timing_reason", ""))
                        with c2:
                            st.metric("技術適合性", proposal.get("tech_fit_score", "-"))
                            st.caption(proposal.get("tech_fit_reason", ""))

                        bottleneck_text = proposal.get("bottleneck", "特になし")
                        solution_text = proposal.get("bottleneck_solution", "特になし")

                        st.warning(f"**最大のボトルネック**: {bottleneck_text}")
                        st.success(f"**解決策**: {solution_text}")

                        st.markdown("#### 🏃 次の具体的なアクション")
                        next_actions = proposal.get("next_actions", [])
                        if next_actions:
                            for action in next_actions:
                                person = action.get("person", "担当未定")
                                task = action.get("action", "タスク内容未定義")
                                st.markdown(f"- **{person}**: {task}")
                        else:
                            st.write("現在提示できる具体的なアクションはありません。")
            else:
                st.write("ピボット提案はありません。")

        with tab_3c:
            tier2 = stage2.get("tier2", {})
            if tier2:
                cust_data = tier2.get("customer", {})
                comp_data = tier2.get("competitor", {})
                co_data = tier2.get("company", {})

                with st.container():
                    c_title, c_content = st.columns([1, 4])
                    with c_title:
                        st.markdown("### 🧑‍🤝‍🧑 Customer")
                        st.caption("市場・顧客")
                    with c_content:
                        st.write(cust_data.get("summary", "情報なし"))
                        for insight in cust_data.get("key_insights", []):
                            st.write(f"・{insight}")
                st.divider()

                with st.container():
                    c_title, c_content = st.columns([1, 4])
                    with c_title:
                        st.markdown("### ⚔️ Competitor")
                        st.caption("競合環境")
                    with c_content:
                        st.write(comp_data.get("summary", "情報なし"))

                        white_space = comp_data.get("white_space", "不明")
                        our_adv = comp_data.get("our_advantage", "不明")

                        st.write(f"**空白地帯**: {white_space}")
                        st.write(f"**自社優位性**: {our_adv}")

                        for insight in comp_data.get("key_insights", []):
                            st.write(f"・{insight}")
                st.divider()

                with st.container():
                    c_title, c_content = st.columns([1, 4])
                    with c_title:
                        st.markdown("### 🏢 Company")
                        st.caption("自社状況")
                    with c_content:
                        if co_data:
                            st.write(co_data.get("summary", "情報なし"))

                            reusable = co_data.get("reusable_assets", [])
                            if reusable:
                                st.markdown("**武器になる資産**")
                                for asset in reusable:
                                    st.write(f"・{asset}")

                            key_persons = co_data.get("key_persons", [])
                            if key_persons:
                                st.markdown("**キーパーソン**")
                                for p in key_persons:
                                    p_name = p.get("name", "氏名不明")
                                    p_role = p.get("role", "役職不明")
                                    st.write(f"・**{p_name}**: {p_role}")

                            lessons = co_data.get("lessons_learned", "")
                            if lessons:
                                st.write(f"**過去の学び**: {lessons}")

        with tab_graph:
            st.subheader("関連情報ネットワーク")
            if vector_results:
                result_ids = {r.get("id") for r in vector_results if "id" in r}
                try:
                    neighbor_ids = {
                        nb.get("id")
                        for nb in get_neighbors(list(result_ids), graph=G)
                        if "id" in nb
                    }
                except Exception:
                    neighbor_ids = set()

                highlighted_ids = result_ids | neighbor_ids
                render_graph(highlighted_ids)
                st.caption("🟡 検索ヒット　🟢 技術　🔵 人物　🟠 市場　🟣 過去PJ")
            else:
                st.warning(
                    "検索結果が取得できませんでした。検索キーワード（ターゲット市場やアセット）を変更して、再度お試しください。"
                )

        st.markdown("</div>", unsafe_allow_html=True)