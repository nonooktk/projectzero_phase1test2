# SKILLS.md — Claudeが習得すべき技術スキル一覧

> このファイルはPROJECT ZEROの開発において、Claudeが正確なコード生成を行うために
> 必要な技術知識をまとめたリファレンスです。
> 各メンバーが「Claudeに依頼する前に読む」ガイドとしても使用してください。

---

## 技術スタック対応表

| 担当 | 必要なスキル |
|---|---|
| Aさん（データ＆AI） | ChromaDB / sentence-transformers / OpenAI API / JSON操作 |
| Bさん（グラフ＆ロジック） | NetworkX / PyVis / Python辞書・リスト操作 |
| Cさん（UI） | Streamlit / PyVis埋め込み / Python基礎 |

---

## SKILL 01 — ChromaDB（セマンティック検索）

### 役割
`retrieval/vector_store.py` で使用。JSONデータをベクトル化して保存し、意味の近さで検索する。

### 基本パターン

```python
import chromadb
from sentence_transformers import SentenceTransformer

# 初期化
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("project_zero")
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# データ投入
def add_documents(documents: list[dict]):
    """
    documents: [{"id": "tech_001", "content": "...", "source": "internal"}, ...]
    """
    ids       = [d["id"] for d in documents]
    contents  = [d["content"] for d in documents]
    metadatas = [{"source": d["source"]} for d in documents]
    embeddings = model.encode(contents).tolist()

    collection.add(
        ids=ids,
        documents=contents,
        metadatas=metadatas,
        embeddings=embeddings
    )

# 検索
def search(query: str, n: int = 5) -> list[dict]:
    query_embedding = model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n,
        include=["documents", "metadatas", "distances"]
    )
    return [
        {
            "id":       results["ids"][0][i],
            "content":  results["documents"][0][i],
            "source":   results["metadatas"][0][i]["source"],
            "score":    1 - results["distances"][0][i]  # 距離→類似度に変換
        }
        for i in range(len(results["ids"][0]))
    ]
```

### 日本語に強いモデル
```python
# 日本語テキストには以下を使う（英語モデルより精度が高い）
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
```

### よくあるエラーと対処

| エラー | 原因 | 対処 |
|---|---|---|
| `IDAlreadyExistsError` | 同じIDを2回投入した | 初期化時にコレクションを削除してから再投入 |
| `InvalidDimensionException` | モデルを変えてDBが残っている | `./chroma_db`フォルダを削除して再実行 |
| 検索結果がおかしい | 日本語が英語モデルで処理されている | multilingualモデルを使う |

---

## SKILL 02 — NetworkX + GraphRAG（グラフ検索）

### 役割
`retrieval/graph_search.py` で使用。nodes.jsonとedges.jsonからグラフを構築し、関連ノードを辿る。

### 基本パターン

```python
import json
import networkx as nx

def build_graph() -> nx.DiGraph:
    """nodes.json / edges.jsonからグラフを構築"""
    with open("data/graph/nodes.json") as f:
        nodes_data = json.load(f)
    with open("data/graph/edges.json") as f:
        edges_data = json.load(f)

    G = nx.DiGraph()

    for node in nodes_data["nodes"]:
        G.add_node(node["id"], **node)  # 全フィールドをノード属性として保持

    for edge in edges_data["edges"]:
        G.add_edge(
            edge["source"],
            edge["target"],
            relation=edge["relation"],
            weight=edge["weight"]
        )
    return G

def get_neighbors(G: nx.DiGraph, node_ids: list[str]) -> list[dict]:
    """
    指定ノードIDリストからdepth=1で隣接ノードを取得
    返り値: ノード情報の辞書リスト
    """
    result = []
    visited = set(node_ids)

    for node_id in node_ids:
        if node_id not in G:
            continue
        for neighbor in G.neighbors(node_id):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            edge_data = G.edges[node_id, neighbor]
            node_data = dict(G.nodes[neighbor])
            node_data["reached_via"] = edge_data["relation"]
            node_data["from_node"]   = node_id
            result.append(node_data)

    return result
```

### Context Builderへの統合

```python
def build_context(chroma_results: list[dict], graph_neighbors: list[dict]) -> dict:
    """ChromaDB結果とGraphRAG結果を3軸テキストに整形"""
    external, internal, org = [], [], []

    for item in chroma_results:
        src = item["source"]
        line = f"- {item['content']}"
        if src == "external":  external.append(line)
        elif src == "internal": internal.append(line)
        elif src == "persons":  org.append(line)

    for node in graph_neighbors:
        line = f"- [{node.get('reached_via','')}] {node.get('name','')}: {node.get('description','')}"
        ntype = node.get("type", "")
        if ntype in ("市場", "規制", "競合"):  external.append(line)
        elif ntype in ("技術", "過去PJ"):      internal.append(line)
        elif ntype == "人物":                  org.append(line)

    return {
        "external_context": "\n".join(external) or "（該当データなし）",
        "internal_context": "\n".join(internal) or "（該当データなし）",
        "org_context":      "\n".join(org)      or "（該当データなし）",
    }
```

---

## SKILL 03 — OpenAI API（GPT-4o-mini呼び出し）

### 役割
`llm/analyzer.py` で使用。Stage1（3軸個別分析）とStage2（統合提案）を呼び出す。

### 基本パターン

```python
import json
import re
from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

def call_gpt(prompt: str, system: str = "あなたは新規事業開発の専門家です。") -> str:
    """GPT-4o-miniを呼び出してテキストを返す"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.3,  # 安定した出力のため低めに設定
    )
    return response.choices[0].message.content

def call_gpt_json(prompt: str) -> dict:
    """JSONを返すことが期待されるGPT呼び出し"""
    raw = call_gpt(prompt)
    # コードブロックが含まれている場合の除去
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        # パースに失敗した場合はエラー情報付きで返す
        return {"error": str(e), "raw": raw}
```

### Stage1の呼び出し例

```python
from llm.prompts import PROMPT_EXTERNAL, PROMPT_INTERNAL, PROMPT_ORG

def run_stage1(context: dict) -> dict:
    return {
        "external": call_gpt_json(PROMPT_EXTERNAL.format(
            external_context=context["external_context"]
        )),
        "internal": call_gpt_json(PROMPT_INTERNAL.format(
            internal_context=context["internal_context"]
        )),
        "org":      call_gpt_json(PROMPT_ORG.format(
            org_context=context["org_context"]
        )),
    }
```

### よくあるエラーと対処

| エラー | 原因 | 対処 |
|---|---|---|
| `AuthenticationError` | APIキーが間違っている | `config.py`のキーを確認 |
| `JSONDecodeError` | GPTがJSON以外を返した | `call_gpt_json`の正規表現でコードブロックを除去 |
| `RateLimitError` | API呼び出しが多すぎる | `time.sleep(1)`を追加して間隔を空ける |

---

## SKILL 04 — prompts.py（プロンプト定数管理）

### 役割
`llm/prompts.py` で使用。全プロンプトをここに集約し、調整を1ファイルで完結させる。

### 基本パターン

```python
# llm/prompts.py

PROMPT_EXTERNAL = """
以下の市場・規制・競合データを元に「今このテーマで参入すべきか」を評価してください。

評価観点：
- 市場タイミング（◎/○/△/×）と根拠
- 競合の空白地帯（White Space）の有無
- 規制・政策タイムライン上のリスクと機会

【データ】
{external_context}

必ずJSON形式のみで返すこと（説明文不要）：
{{"timing_score": "◎", "white_space": "...", "regulation_risk": "...", "summary": "..."}}
"""

PROMPT_INTERNAL = """
以下の社内データを元に「自社でこのテーマをやれるか」を評価してください。

評価観点：
- 保有技術・アセットの適合度（◎/○/△/×）と根拠
- 過去の類似失敗事例と、その失敗条件が今も存在するか
- 現時点で解決済みの条件と残存リスク

【データ】
{internal_context}

必ずJSON形式のみで返すこと（説明文不要）：
{{"tech_fit_score": "◎", "past_failures": [], "resolved_conditions": [], "remaining_risks": [], "summary": "..."}}
"""

PROMPT_ORG = """
以下のキーマンデータを元に「誰と動くべきか」を特定してください。

評価観点：
- 知見を持つキーマンと確認すべき具体的内容
- 推奨する最初のアクション（誰に・何を）

【データ】
{org_context}

必ずJSON形式のみで返すこと（説明文不要）：
{{"key_persons": [], "next_actions": [], "summary": "..."}}
"""

PROMPT_STAGE2 = """
以下の3軸分析結果を統合し、新規事業案を3つ提案してください。

【①外部環境分析結果】
{stage1_external}

【②社内コンテキスト分析結果】
{stage1_internal}

【③組織適合分析結果】
{stage1_org}

各提案に必ず含めること：
- 事業概要（2〜3行）
- 市場タイミング評価（◎○△×）と根拠
- 技術適合評価（◎○△×）と根拠
- 想定ボトルネックと対処方法
- ネクストアクション（誰に・何を確認するか）

また承認者向けの1段落サマリーも生成すること。
必ずJSON形式のみで返すこと（説明文不要）：
{{
  "proposals": [
    {{
      "title": "...",
      "summary": "...",
      "timing_score": "◎",
      "timing_reason": "...",
      "tech_fit_score": "◎",
      "tech_fit_reason": "...",
      "bottleneck": "...",
      "bottleneck_solution": "...",
      "next_actions": [{{"person": "...", "action": "..."}}]
    }}
  ],
  "approver_summary": "..."
}}
"""
```

### プロンプト調整のコツ

```
精度が上がりやすい工夫：
1. 「必ずJSON形式のみで返すこと（説明文不要）」を明記する
2. 期待するJSONの構造をサンプルとして書く
3. temperatureを0.3以下に設定する（安定した出力）
4. 「◎/○/△/×」の判定基準を具体的に書く（例：「市場が年率10%以上成長なら◎」）
```

---

## SKILL 05 — Streamlit（UI構築）

### 役割
`app.py` で使用。全画面をここに集約する。

### 基本パターン（画面構成）

```python
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="PROJECT ZERO", layout="wide")
st.title("新規事業判断支援システム")

# ── 入力エリア ──
query = st.text_input("新規事業のテーマを入力してください",
                       placeholder="例：ビルエネルギー管理で新事業を考えたい")
run_btn = st.button("分析開始", type="primary")

if run_btn and query:

    with st.spinner("Stage1: 3軸分析中..."):
        # ここで retrieval → llm を呼び出す
        pass

    # ── 3軸評価パネル ──
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("① 今やるべきか")
        st.metric("市場タイミング", "◎")
        with st.expander("根拠を見る"):
            st.write("欧州規制2027年施行前の参入好機...")

    with col2:
        st.subheader("② 自社でやれるか")
        st.metric("技術適合", "◎")
        with st.expander("根拠を見る"):
            st.write("軟質素材成形技術（特許3件）が直接適用可能...")

    with col3:
        st.subheader("③ 誰とやるか")
        st.metric("推奨キーマン", "2名")
        with st.expander("詳細を見る"):
            st.write("山田さん（法務）：薬機法認証の確認...")

    st.divider()

    # ── 提案タブ ──
    with st.spinner("Stage2: 提案生成中..."):
        pass

    tab1, tab2, tab3 = st.tabs(["案1", "案2", "案3"])
    with tab1:
        st.subheader("医療向け軟質生分解素材事業")
        st.write("事業概要テキスト...")
        with st.expander("承認者向けサマリー"):
            st.info("承認者向け1段落サマリー...")

    st.divider()

    # ── PyVis グラフ ──
    st.subheader("関係性マップ")
    # PyVisのHTMLを埋め込む
    with open("graph.html", "r", encoding="utf-8") as f:
        graph_html = f.read()
    components.html(graph_html, height=500)
```

### よく使うコンポーネント早見表

| コンポーネント | 使いどころ | コード例 |
|---|---|---|
| `st.columns(3)` | 3軸を横並びに表示 | `col1, col2, col3 = st.columns(3)` |
| `st.metric()` | スコア（◎○△×）を目立たせる | `st.metric("タイミング", "◎")` |
| `st.tabs()` | 案1/案2/案3の切り替え | `tab1, tab2, tab3 = st.tabs(["案1","案2","案3"])` |
| `st.expander()` | 根拠詳細を折りたたむ | `with st.expander("根拠"):` |
| `st.spinner()` | 処理中の表示 | `with st.spinner("分析中..."):` |
| `st.info()` | 青いボックスで強調 | `st.info("承認者サマリー...")` |
| `st.divider()` | セクション区切り線 | `st.divider()` |

---

## SKILL 06 — PyVis（グラフ可視化）

### 役割
`app.py` の中でグラフを可視化してStreamlitに埋め込む。

### 基本パターン

```python
from pyvis.network import Network
import streamlit.components.v1 as components

def render_graph(G, highlight_ids: list[str] = None) -> str:
    """
    NetworkXグラフをPyVisでHTMLに変換して返す
    highlight_ids: 強調表示するノードIDリスト
    """
    net = Network(
        height="480px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white",
        directed=True
    )

    # ノードタイプ別の色設定
    color_map = {
        "技術":   "#4f8ef7",
        "人物":   "#fbbf24",
        "市場":   "#34d399",
        "過去PJ": "#a78bfa",
        "課題":   "#f87171",
    }

    for node_id, attrs in G.nodes(data=True):
        ntype  = attrs.get("type", "")
        color  = color_map.get(ntype, "#ffffff")
        size   = 30 if (highlight_ids and node_id in highlight_ids) else 15
        border = "#ffffff" if (highlight_ids and node_id in highlight_ids) else color

        net.add_node(
            node_id,
            label=attrs.get("name", node_id),
            color={"background": color, "border": border},
            size=size,
            title=attrs.get("description", ""),  # ホバー時に表示
        )

    for src, tgt, attrs in G.edges(data=True):
        net.add_edge(
            src, tgt,
            label=attrs.get("relation", ""),
            width=attrs.get("weight", 0.5) * 3,
            color="#444466"
        )

    net.set_options("""
    {
      "physics": {"stabilization": {"iterations": 100}},
      "edges": {"smooth": {"type": "curvedCW", "roundness": 0.2}}
    }
    """)

    html_path = "/tmp/graph.html"
    net.save_graph(html_path)
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

# Streamlitへの埋め込み
graph_html = render_graph(G, highlight_ids=["tech_001", "market_001"])
components.html(graph_html, height=500, scrolling=False)
```

### よくあるエラーと対処

| エラー | 原因 | 対処 |
|---|---|---|
| グラフが表示されない | HTMLファイルの保存先がない | `/tmp/graph.html` に保存する |
| ノードが重なる | physicsが未設定 | `net.set_options`でiterations増やす |
| 文字化け | エンコーディング指定なし | `open(..., encoding="utf-8")` を明記 |

---

## SKILL 07 — config.py とAPIキー管理

### 役割
APIキーを安全に管理する。コードに直書きしない。

### 基本パターン

```python
# config.py
import os

# 環境変数から読む（推奨）
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# 環境変数が設定されていない場合のフォールバック（開発時のみ）
if not OPENAI_API_KEY:
    OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxx"  # 開発時のみここに記載

# 他の設定
CHROMA_DB_PATH  = "./chroma_db"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
GPT_MODEL       = "gpt-4o-mini"
GPT_TEMPERATURE = 0.3
SEARCH_TOP_K    = 5
```

```python
# 他のファイルからの読み込み方
from config import OPENAI_API_KEY, CHROMA_DB_PATH
```

### .gitignoreへの追加（必須）

```
# .gitignore
config.py        # APIキーを含むため
chroma_db/       # DBファイルは除外
__pycache__/
*.pyc
```

---

## SKILL 08 — JSON操作（データ読み込み）

### 役割
全モジュールで共通して使う。JSONファイルの読み込みパターン。

### 基本パターン

```python
import json
from pathlib import Path

def load_json(filepath: str) -> dict:
    """JSONファイルを読み込む"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def flatten_for_chroma(data: dict, source: str) -> list[dict]:
    """
    JSONの各カテゴリを1件ずつの辞書に展開する
    ChromaDBへの投入用
    """
    documents = []
    for category, items in data.items():
        if not isinstance(items, list):
            continue
        for item in items:
            content_parts = [
                item.get("name", ""),
                item.get("description", ""),
                " ".join(item.get("tags", [])),
            ]
            # failure_casesの場合はconditions_nowも含める
            if "conditions_now" in item:
                for cond, status in item["conditions_now"].items():
                    content_parts.append(f"{cond}：{status}")

            documents.append({
                "id":       f"{source}_{item['id']}",
                "content":  " ".join(filter(None, content_parts)),
                "source":   source,
                "category": category,
            })
    return documents
```

### 使用例

```python
internal_data = load_json("data/internal.json")
external_data = load_json("data/external.json")
persons_data  = load_json("data/persons.json")

all_docs = (
    flatten_for_chroma(internal_data, "internal") +
    flatten_for_chroma(external_data, "external") +
    flatten_for_chroma(persons_data,  "persons")
)
# → ChromaDBに投入
add_documents(all_docs)
```

---

## よくあるデバッグパターン

### ChromaDBが空で返ってくる

```python
# 確認方法
print(collection.count())  # 投入件数を確認
# → 0 なら投入できていない。add_documents()を確認
```

### GPTがJSONを返さない

```python
# デバッグ用：生レスポンスを確認
raw = call_gpt(prompt)
print("=== GPT RAW RESPONSE ===")
print(raw)
print("========================")
# → JSONコードブロック（```json）が含まれていたらre.subで除去
```

### Streamlitが更新されない

```bash
# キャッシュをクリアして再起動
streamlit run app.py --server.runOnSave true
```

### NetworkXにノードが見つからない

```python
# ノード存在確認
print(list(G.nodes())[:10])  # 最初の10ノードを確認
print(G.number_of_nodes(), G.number_of_edges())
```
