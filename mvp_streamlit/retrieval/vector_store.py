"""
vector_store.py — ChromaDB によるベクトル検索モジュール

担当: Aさん（データ＆AI担当）

【このファイルの役割】
- data/ 以下の3つのJSONファイルをChromaDBに投入する
- クエリ文字列を受け取り、意味的に近いデータを上位N件返す

【使うライブラリ】
- chromadb: ベクトルデータベース
- sentence-transformers: テキストをベクトルに変換するEmbeddingモデル
"""

import json
import os

import chromadb
from sentence_transformers import SentenceTransformer

# --- 定数 ---
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
COLLECTION_NAME = "project_zero"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 軽量で高速な多言語対応モデル


def load_data() -> list[dict]:
    """
    3つのJSONファイルを読み込み、1つのリストにまとめて返す。

    Returns:
        list[dict]: 全データのリスト。各データに "source" フィールドを付与する。
        例:
        [
          {"id": "ext_001", "content": "...", "source": "external"},
          {"id": "tech_001", "content": "...", "source": "internal"},
          ...
        ]
    """

    all_data = []

    # ファイルごとに (ファイルパス, sourceラベル) のペアを定義
    files = [
        (os.path.join(DATA_DIR, "external.json"), "external"),
        (os.path.join(DATA_DIR, "internal.json"), "internal"),
        (os.path.join(DATA_DIR, "persons.json"), "persons"),
    ]

    for filepath, source in files:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            item["source"] = source
        all_data += data

    return all_data


def build_collection(
    client: chromadb.Client, model: SentenceTransformer
) -> chromadb.Collection:
    """
    ChromaDBにデータを投入してコレクションを作成・返す。
    既にコレクションが存在する場合はそのまま返す。

    Args:
        client: ChromaDB クライアント
        model: Embeddingモデル

    Returns:
        chromadb.Collection: データが投入されたコレクション
    """

    collection = client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    data = load_data()

    ids = [item["id"] for item in data]
    texts = [item["content"] for item in data]
    metadatas = [{"source": item["source"]} for item in data]

    embeddings = model.encode(texts)

    collection.add(
        ids=ids, embeddings=embeddings.tolist(), documents=texts, metadatas=metadatas
    )

    return collection


# --- モジュールレベルのキャッシュ（初回呼び出し時に1回だけ構築）---
_client = None
_model = None
_collection = None


def _get_collection():
    """ChromaDB クライアント・モデル・コレクションをキャッシュして返す。"""
    global _client, _model, _collection
    if _collection is not None:
        return _collection, _model
    _client = chromadb.Client()
    _model = SentenceTransformer(EMBEDDING_MODEL)
    _collection = build_collection(_client, _model)
    return _collection, _model


def search(query: str, n: int = 5) -> list[dict]:
    """
    クエリ文字列を受け取り、意味的に近いデータを上位N件返す。

    Args:
        query (str): 検索クエリ文字列
        n (int): 返す件数（デフォルト5）

    Returns:
        list[dict]: 検索結果のリスト
        例:
        [
          {
            "id": "tech_001",
            "content": "高精度センサー製造技術...",
            "score": 0.91,
            "source": "internal"
          },
          ...
        ]
    """

    collection, model = _get_collection()

    query_vector = model.encode(query).tolist()

    raw = collection.query(query_embeddings=[query_vector], n_results=n)

    results = []
    ids = raw["ids"][0]
    documents = raw["documents"][0]
    distances = raw["distances"][0]
    metadatas = raw["metadatas"][0]

    for i in range(len(ids)):
        results.append(
            {
                "id": ids[i],
                "content": documents[i],
                "score": round(1 - distances[i], 4),
                "source": metadatas[i]["source"],
            }
        )

    return results


if __name__ == "__main__":
    # 動作確認用: このファイルを直接実行してテストする
    # 実行: python retrieval/vector_store.py
    results = search("ビルエネルギー管理")
    for r in results:
        print(r)
