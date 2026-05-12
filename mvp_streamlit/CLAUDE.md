# CLAUDE.md — PROJECT ZERO 開発ガイド

> このファイルはClaude Code（またはClaude）がプロジェクトを支援する際に参照する作業指示書です。
> 開発メンバーが生成AIを使ってコードを書く際の文脈・制約・ルールをここに集約しています。

---

## 1. プロジェクト概要

### システム名
新規事業判断支援システム（PROJECT ZERO）

### 一言ミッション
「この提案、うちでやれるか？今やるべきか？」に即答できる意思決定基盤のMVPを作る。

### 承認者
黒崎 厳（CDO・55歳）。徹底した合理主義。求めるのは「動くコード」と「ビジネスインパクト」。
「議論は十分だ。私が必要としているのは、100の改善案ではなく、1つの動くコードだ。」

### 開発前提
- **チーム**：3名（A：データ＆AI担当 / B：グラフ＆ロジック担当 / C：UI担当）
- **期間**：2週間（10営業日）
- **経験**：全員アプリ制作未経験・生成AI活用前提
- **データ**：ダミーデータで可
- **目標**：役員会デモで継続投資の承認を得る

---

## 2. アーキテクチャ

### データフロー（全体）

```
ユーザー入力（テーマ）
        ↓
クエリを3軸に固定テンプレートで分解
 ├ ① 今やるべきか    → external.json を検索
 ├ ② 自社でやれるか  → internal.json を検索
 └ ③ 誰とやるか      → persons.json を検索
        ↓
ChromaDB（1コレクション・全データ統合）
        ↓
GraphRAG（静的グラフ・depth=1）
        ↓
Context Builder（検索結果を3軸テキストに連結）
        ↓
GPT-4o-mini Stage1（3軸を個別分析・◎○△×スコア生成）
        ↓
GPT-4o-mini Stage2（3軸を統合・事業案3つ＋承認者サマリー生成）
        ↓
Streamlit表示（3軸パネル／提案タブ／PyVisグラフ）
```

### MVPで実装しないもの（将来対応）

| 項目 | 理由 |
|---|---|
| Graph Updater（エッジ自動蓄積） | 静的グラフで十分 |
| クエリ自動分解 | 固定テンプレートで代替 |
| ChromaDB 3コレクション分割 | 1コレクションで十分 |
| 部署・パートナーDB | persons.jsonのみで十分 |

---

## 3. ディレクトリ構成

```
project/
├── app.py               # Streamlitメイン。UI・画面制御はここに集約
├── config.py            # APIキーのみ記載
├── requirements.txt     # 依存ライブラリ一覧
│
├── data/
│   ├── external.json    # ① 市場・規制・競合（社外データ）
│   ├── internal.json    # ② 技術・過去PJ・失敗事例（社内データ）
│   ├── persons.json     # ③ キーマン情報
│   └── graph/
│       ├── nodes.json   # グラフノード（手動設計）
│       └── edges.json   # グラフエッジ（静的・手動設計）
│
├── retrieval/
│   ├── vector_store.py  # ChromaDB初期化・検索（1コレクション）
│   └── graph_search.py  # NetworkXグラフ構築＋検索
│
└── llm/
    ├── analyzer.py      # Stage1＋Stage2のGPT呼び出し
    └── prompts.py       # プロンプト文字列の定数管理
```

**合計9ファイル。これ以上増やさない。** 追加が必要な場合はメンバー全員で合意すること。

---

## 4. 技術スタック

```
pip install streamlit chromadb networkx pyvis sentence-transformers openai
```

| レイヤー | 技術 | 役割 |
|---|---|---|
| UI | Streamlit | 画面全体 |
| セマンティック検索 | ChromaDB | 意味で近いデータを検索 |
| グラフ検索 | NetworkX | 関係性を辿る検索 |
| グラフ可視化 | PyVis | インタラクティブグラフ表示 |
| Embedding | sentence-transformers | テキストをベクトルに変換 |
| LLM | OpenAI GPT-4o-mini | 分析・提案生成 |

---

## 5. メンバー体制と担当ファイル

### Aさん：データ＆AI担当

**担当ファイル**
- `data/external.json`
- `data/internal.json`
- `data/persons.json`
- `retrieval/vector_store.py`
- `llm/analyzer.py`
- `llm/prompts.py`

**タスク詳細**
- ダミーデータJSONの作成・品質確認
- ChromaDBへのデータ投入・検索動作確認
- GPT-4o-miniとの接続・レスポンスのJSONパース確認
- Stage1・Stage2プロンプトの調整（出力品質を上げる）

**Claudeへの依頼例**
```
vector_store.pyを作って。
external.json / internal.json / persons.jsonを読み込んで
ChromaDBの1つのコレクションに投入し、
クエリ文字列を渡すと上位5件を返す search(query, n=5) 関数を実装して。
```

---

### Bさん：グラフ＆ロジック担当

**担当ファイル**
- `data/graph/nodes.json`
- `data/graph/edges.json`
- `retrieval/graph_search.py`

**タスク詳細**
- nodes.json / edges.jsonのスキーマ設計（班ディスカッション主導）
- NetworkXによるグラフ構築
- クエリに近いエントリーノードを起点にdepth=1で関連ノードを取得する関数の実装
- ChromaDB検索結果と組み合わせるContext Builder部分の実装

**Claudeへの依頼例**
```
graph_search.pyを作って。
nodes.jsonとedges.jsonを読み込んでNetworkXグラフを構築し、
node_idのリストを受け取ってdepth=1で隣接ノードを返す
get_neighbors(node_ids) 関数を実装して。
```

---

### Cさん：UI担当

**担当ファイル**
- `app.py`（メイン）

**タスク詳細**
- Streamlitで3軸評価パネルの並列表示
- 提案タブ（案1/案2/案3）の実装
- 承認者向けサマリーのexpander表示
- PyVisグラフのStreamlit埋め込み
- 提案に関連するノードのハイライト処理

**Claudeへの依頼例**
```
app.pyのUI部分を作って。
st.columns(3)で3軸（外部環境・社内・組織）を並列表示し、
各軸にst.metric()でスコア（◎○△×）を表示、
st.expander()で根拠詳細を折りたたむ形にして。
```

---

## 6. 実装フロー（10日間）

### Week1：作る

| Day | 全員 | Aさん | Bさん | Cさん |
|---|---|---|---|---|
| 1-2 | Python環境・APIキー設定確認 | JSONダミーデータ作成 | nodes/edges設計議論 | Streamlit起動確認 |
| 3-4 | — | ChromaDB投入・検索確認 | NetworkXグラフ構築確認 | 画面骨格の実装 |
| 5 | **JSONスキーマ3者合意**（後述） | GPT接続確認 | Context Builder実装 | パネル配置確定 |

### Week2：繋いで磨く

| Day | 作業内容 |
|---|---|
| 6-7 | app.pyで3者の成果物を結合・一気通貫テスト |
| 8-9 | デモシナリオに合わせた調整・バグ修正 |
| 10 | デモリハーサル・最終確認 |

---

## 7. Day5 インターフェース合意（最重要）

Week1の最終日にこれを合意しないとWeek2が詰まる。

### 合意すべき3点

**① ChromaDB検索結果の形式（AさんとBさんの境界）**
```python
# vector_store.pyが返す形式をここで決める
[
  {
    "id": "tech_001",
    "content": "高精度センサー製造技術。精度±0.01%。IoT・製造業向け。",
    "score": 0.91,
    "source": "internal"   # どのJSONから来たか
  },
  ...
]
```

**② Context Builderが作るテキストの形式（BさんとAさんの境界）**
```python
# graph_search.pyが返す形式をここで決める
{
  "external_context": "【市場情報】...\n【規制情報】...",
  "internal_context": "【保有技術】...\n【失敗事例】...",
  "org_context":      "【キーマン】..."
}
```

**③ Stage2が返すJSONの形式（AさんとCさんの境界）**
```python
# analyzer.pyが返す形式をここで決める
{
  "proposals": [
    {
      "title": "...",
      "summary": "...",
      "timing_score": "◎",
      "timing_reason": "...",
      "tech_fit_score": "◎",
      "tech_fit_reason": "...",
      "bottleneck": "...",
      "bottleneck_solution": "...",
      "next_actions": [
        {"person": "...", "action": "..."}
      ]
    }
  ],
  "approver_summary": "..."
}
```

---

## 8. レビュー方法

### レビューの原則

未経験チームのため、**コードレビューよりも「動作確認レビュー」を優先する。**
「コードが正しいか」より「動いて正しい結果が出るか」を確認する。

### 各フェーズのレビューチェックリスト

**Phase 1（Day1-2）：データ確認**
- [ ] external.json / internal.json / persons.jsonが正しいJSON形式か（JSONLint等で確認）
- [ ] failure_casesのconditions_nowが3パターン（全解決・一部解決・未解決）揃っているか
- [ ] 全IDが一意か（tech_001の重複などがないか）
- [ ] tagsが各データに複数入っているか

**Phase 2（Day3-4）：単体確認**
- [ ] `python retrieval/vector_store.py` を実行してエラーが出ないか
- [ ] 検索クエリを渡して上位5件が返ってくるか
- [ ] `python retrieval/graph_search.py` を実行してグラフが構築されるか
- [ ] `streamlit run app.py` で画面が表示されるか

**Phase 3（Day5）：インターフェース確認**
- [ ] Day5合意の3フォーマットがドキュメント化されたか
- [ ] Aさんのダミー出力をCさんがUIに表示できるか（モック動作）

**Phase 4（Day6-7）：一気通貫確認**
- [ ] テーマを入力してStage1のスコアが表示されるか
- [ ] Stage2の提案3案がタブで表示されるか
- [ ] PyVisグラフが表示されるか
- [ ] 承認者サマリーがexpanderで表示されるか

**Phase 5（Day8-10）：デモ品質確認**
- [ ] デモシナリオ（3テーマ分）で一気通貫が動くか
- [ ] fail_002（BEMS・全条件解決）でGOサインが出るか
- [ ] fail_003（ウェアラブル・条件未変化）でNOサインが出るか
- [ ] PyVisグラフで提案関連ノードがハイライトされるか
- [ ] 承認者サマリーの文章が説得力のあるものになっているか

### レビュー方法（具体的な進め方）

```
毎日15分の同期ミーティング
  ├ 昨日やったこと（1分/人）
  ├ 今日やること（1分/人）
  └ 詰まっていること（残り時間で解決）

詰まったときの対応フロー
  1. まずClaude Codeに「エラーメッセージ」と「やりたいこと」を貼る
  2. 30分解決しなければチームに共有
  3. チームでも30分解決しなければ実装を簡略化する方向で判断
     （動くことが最優先。完璧より前進）
```

---

## 9. Claudeへの依頼ルール

このプロジェクトでClaude（またはClaude Code）を使う際のルール。

### 依頼時に必ず伝えること

```
1. 担当ファイル名（例：retrieval/vector_store.py）
2. 関数名と引数・戻り値の形式
3. 使用するライブラリ（例：chromadb, sentence-transformers）
4. エラーが出た場合はエラーメッセージ全文
```

### 依頼テンプレート

```
【ファイル】retrieval/vector_store.py
【やりたいこと】ChromaDBに3つのJSONを投入して検索できるようにしたい
【使うライブラリ】chromadb, sentence-transformers
【入力】data/external.json, data/internal.json, data/persons.json
【出力】search(query: str, n: int = 5) -> list[dict] 関数
【制約】1コレクションに全データを統合する。sourceフィールドでどのJSONか識別できるようにする
```

### やってはいけないこと

- APIキーをコードに直書きしない（必ず`config.py`から読む）
- ファイルを9個以上に増やさない（合意なしに新ファイルを作らない）
- MVPで実装しないと決めた機能（Graph Updater等）を追加しない
- `requirements.txt`にないライブラリを無断でインストールしない

---

## 10. デモシナリオ（本番想定）

黒崎CDOへのデモで使う3つのテーマ。事前にこの3テーマで動作確認を完了させる。

| # | 入力テーマ | 期待される出力 | 確認ポイント |
|---|---|---|---|
| 1 | 「ビルエネルギー管理で新事業を考えたい」 | BEMS市場◎・fail_002全条件解決→GO | 失敗からの再参入シナリオ |
| 2 | 「医療機器向けに自社技術を活かしたい」 | MEMS医療市場◎・薬機法認証済→GO | 既存実績の横展開シナリオ |
| 3 | 「スマートフォン向けウェアラブルに参入したい」 | B2C条件未解決→NO・B2B2C転換を推奨 | NOを出せることの実証 |

---

## 11. デモで絶対に削らないもの

| 項目 | 理由 |
|---|---|
| failure_casesのconditions_now（3パターン） | GO/NO判断の根拠。これがないとただのチャットボット |
| 承認者サマリーの文章品質 | 黒崎CDOが見るのはここ。プロンプト調整に時間をかける |
| PyVis可視化 | 「ただのチャットボットと違う」という印象を作る。必ず入れる |

---

## 12. 用語定義

| 用語 | 定義 |
|---|---|
| RAG | 検索で関連情報を取得してからLLMに渡す手法 |
| ChromaDB | 意味の近さで検索できるローカルベクトルDB |
| GraphRAG | ノードとエッジで関係性を辿る検索。ChromaDBと組み合わせて使う |
| Stage1 | 3軸（外部・内部・組織）を個別にGPTで分析し◎○△×スコアを生成するステップ |
| Stage2 | Stage1の結果を統合し事業案3つ＋承認者サマリーを生成するステップ |
| ノード | グラフの「点」。技術・人物・市場・過去PJなど |
| エッジ | グラフの「線」。ノード間の関係性（担当できる・応用できる など） |
| conditions_now | 過去の失敗条件が現在解消されているかを記したフィールド。このシステムの核心 |
| 承認者サマリー | 黒崎CDO向けの1段落要約。なぜGO/NOかが一目でわかる文章 |
