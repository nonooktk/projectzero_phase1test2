"use client";

import { FormEvent, useEffect, useState } from "react";
import { AnalysisResponse, createAnalysis } from "../lib/api";

const axisLabels: Record<string, string> = {
  external: "外部環境",
  internal: "社内適合",
  org: "組織体制",
};

const progressSteps = [
  {
    label: "リクエスト受付",
    description: "入力内容をAPIへ送信している。",
    startsAt: 0,
  },
  {
    label: "関連データ検索",
    description: "ChromaDBで市場・社内・人物情報を検索している。",
    startsAt: 2,
  },
  {
    label: "関連ノード補完",
    description: "NetworkXで関係者と関連市場を補完している。",
    startsAt: 6,
  },
  {
    label: "AI評価生成",
    description: "OpenAIで3軸評価、GO/NO、事業提案を生成している。",
    startsAt: 10,
  },
  {
    label: "保存処理",
    description: "Supabaseへ分析結果とジョブ状態を保存している。",
    startsAt: 45,
  },
];

const ideaTemplates = [
  {
    label: "BEMS",
    targetMarket: "国内外の大規模ビルオーナー、商業施設、工場のエネルギー管理部門",
    assets: "BEMS関連の過去事業知見、薄膜太陽電池、社内の省エネ制御技術",
    ideaDetail:
      "既存ビルのエネルギー消費データを収集し、AIで空調・照明・蓄電池運用を最適化する省エネ管理SaaSを提供する。",
  },
  {
    label: "医療",
    targetMarket: "地方中核病院、在宅医療事業者、高齢者施設",
    assets: "ウェアラブルセンサー、画像解析技術、医療機器開発の品質管理ノウハウ",
    ideaDetail:
      "患者のバイタルデータと問診情報を継続取得し、急変リスクを早期検知して医療スタッフの判断を支援するモニタリングサービスを展開する。",
  },
  {
    label: "素材",
    targetMarket: "欧州の大規模農業法人、食品包装メーカー、環境規制対応が必要な製造業",
    assets: "100%植物由来ポリマー、量産プロセス、素材評価データ",
    ideaDetail:
      "環境規制強化を背景に、植物由来ポリマーを農業用フィルムや食品包装材として展開し、廃棄負荷を下げる新素材事業を立ち上げる。",
  },
];

function graphNodePosition(index: number, total: number) {
  if (total <= 1) {
    return { x: 380, y: 170 };
  }
  const angle = (2 * Math.PI * index) / total - Math.PI / 2;
  return {
    x: 380 + Math.cos(angle) * 280,
    y: 170 + Math.sin(angle) * 110,
  };
}

function RelatedGraph({ result }: { result: AnalysisResponse }) {
  const nodes = result.graph_view?.nodes ?? [];
  const edges = result.graph_view?.edges ?? [];
  const positions = new Map(
    nodes.map((node, index) => [node.id, graphNodePosition(index, nodes.length)]),
  );

  if (nodes.length) {
    return (
      <div className="graphPanel">
        <svg className="graphCanvas" role="img" viewBox="0 0 760 340">
          {edges.map((edge) => {
            const source = positions.get(edge.source_id);
            const target = positions.get(edge.target_id);
            if (!source || !target) {
              return null;
            }
            return (
              <g key={`${edge.source_id}-${edge.target_id}-${edge.relation}`}>
                <line
                  className="graphEdge"
                  x1={source.x}
                  x2={target.x}
                  y1={source.y}
                  y2={target.y}
                />
                <text
                  className="graphEdgeLabel"
                  x={(source.x + target.x) / 2}
                  y={(source.y + target.y) / 2}
                >
                  {edge.relation}
                </text>
              </g>
            );
          })}
          {nodes.map((node) => {
            const position = positions.get(node.id) ?? { x: 380, y: 170 };
            return (
              <g className={`graphNode ${node.source}`} key={node.id}>
                <circle cx={position.x} cy={position.y} r="32" />
                <text className="graphNodeLabel" x={position.x} y={position.y - 3}>
                  {node.label}
                </text>
                <text className="graphNodeType" x={position.x} y={position.y + 14}>
                  {node.type}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="relatedPanel">
          {nodes.map((node) => (
            <article className="relatedNode" key={node.id}>
              <div>
                <strong>{node.label}</strong>
                <span>{node.type}</span>
              </div>
              <p>{node.source === "seed" ? "検索結果から接続" : "関連ノードとして補完"}</p>
            </article>
          ))}
        </div>
      </div>
    );
  }

  if (result.graph_results.length) {
    return (
      <div className="relatedPanel">
        {result.graph_results.map((node) => (
          <article className="relatedNode" key={`${node.id}-${node.relation}`}>
            <div>
              <strong>{node.label}</strong>
              <span>{node.type}</span>
            </div>
            <p>{node.relation}</p>
          </article>
        ))}
      </div>
    );
  }

  return <p className="muted">関連ノードはありません。</p>;
}

export default function Home() {
  const [targetMarket, setTargetMarket] = useState("");
  const [assets, setAssets] = useState("");
  const [ideaDetail, setIdeaDetail] = useState("");
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!loading) {
      setElapsedSeconds(0);
      return;
    }

    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [loading]);

  const activeStepIndex = progressSteps.reduce((activeIndex, step, index) => {
    return elapsedSeconds >= step.startsAt ? index : activeIndex;
  }, 0);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const data = await createAnalysis({
        target_market: targetMarket,
        assets,
        idea_detail: ideaDetail,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  function applyTemplate(template: (typeof ideaTemplates)[number]) {
    setTargetMarket(template.targetMarket);
    setAssets(template.assets);
    setIdeaDetail(template.ideaDetail);
    setError("");
    setResult(null);
  }

  return (
    <main className="page">
      <section className="shell">
        <header className="appHeader">
          <div>
            <span className="eyebrow">PROJECT ZERO / DECISION INTEL</span>
            <h1>Tech0 Search</h1>
            <p>新規事業アイデアを入力し、投資判断フローを開始する。</p>
          </div>
          <div className="signalRail" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
        </header>

        <form className="form" onSubmit={onSubmit}>
          <div className="templateBar" aria-label="入力テンプレート">
            <span>Template</span>
            <div>
              {ideaTemplates.map((template) => (
                <button
                  className="templateButton"
                  key={template.label}
                  onClick={() => applyTemplate(template)}
                  type="button"
                >
                  {template.label}
                </button>
              ))}
            </div>
          </div>

          <label className="field">
            ターゲット市場 / 想定顧客
            <input
              value={targetMarket}
              onChange={(event) => setTargetMarket(event.target.value)}
              placeholder="例: 欧州の大規模農業法人"
            />
          </label>

          <label className="field">
            活用したい自社アセット・コア技術
            <input
              value={assets}
              onChange={(event) => setAssets(event.target.value)}
              placeholder="例: 100%植物由来ポリマー"
            />
          </label>

          <label className="field">
            提供価値・事業アイデアの詳細
            <textarea
              required
              value={ideaDetail}
              onChange={(event) => setIdeaDetail(event.target.value)}
              placeholder="例: 環境規制強化を背景に、農業用フィルムとして展開する"
            />
          </label>

          <button className="button" disabled={loading} type="submit">
            {loading ? "分析開始中..." : "分析スタート"}
          </button>
        </form>

        {loading ? (
          <section className="progressPanel" aria-live="polite">
            <div className="progressHeader">
              <div>
                <h2>分析中</h2>
                <p className="muted">
                  初回はモデル読み込みとAI評価で1分前後かかることがある。
                </p>
              </div>
              <span className="statusBadge">{elapsedSeconds}s</span>
            </div>
            <div className="progressTrack">
              {progressSteps.map((step, index) => {
                const state =
                  index < activeStepIndex
                    ? "done"
                    : index === activeStepIndex
                      ? "active"
                      : "waiting";
                return (
                  <article className={`progressStep ${state}`} key={step.label}>
                    <span className="progressDot" />
                    <div>
                      <strong>{step.label}</strong>
                      <p>{step.description}</p>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ) : null}

        {error ? <p className="error">{error}</p> : null}

        {result ? (
          <section className="result">
            <div className="resultHeader">
              <div>
                <h2>分析結果</h2>
                <p className="muted">ID: {result.analysis_id}</p>
              </div>
              <span className="statusBadge">{result.status}</span>
            </div>

            {result.llm_analysis ? (
              <>
                <div className="verdict">
                  <span>GO/NO</span>
                  <strong>{result.llm_analysis.go_no_verdict}</strong>
                </div>
                <p className="summary">{result.summary}</p>

                <h3>3軸評価</h3>
                <div className="scoreGrid">
                  {Object.entries(result.llm_analysis.stage1).map(([axis, value]) => (
                    <article className="scoreCard" key={axis}>
                      <div className="scoreTop">
                        <span>{axisLabels[axis] ?? axis}</span>
                        <strong>{value.score ?? "-"}</strong>
                      </div>
                      <p>{value.reason ?? "評価根拠がありません。"}</p>
                      {value.key_points?.length ? (
                        <ul>
                          {value.key_points.map((point) => (
                            <li key={point}>{point}</li>
                          ))}
                        </ul>
                      ) : null}
                    </article>
                  ))}
                </div>

                <h3>事業提案</h3>
                <div className="proposalList">
                  {result.llm_analysis.stage2.proposals?.map((proposal, index) => (
                    <article className="proposal" key={`${proposal.title}-${index}`}>
                      <h4>{proposal.title ?? `提案 ${index + 1}`}</h4>
                      <p>{proposal.summary}</p>
                      <div className="proposalMeta">
                        <span>タイミング: {proposal.timing_score ?? "-"}</span>
                        <span>技術適合: {proposal.tech_fit_score ?? "-"}</span>
                      </div>
                      <p className="muted">{proposal.timing_reason}</p>
                      <p className="muted">{proposal.tech_fit_reason}</p>
                      <p>
                        <strong>ボトルネック:</strong> {proposal.bottleneck ?? "-"}
                      </p>
                      <p>
                        <strong>解決策:</strong> {proposal.bottleneck_solution ?? "-"}
                      </p>
                      {proposal.next_actions?.length ? (
                        <ul>
                          {proposal.next_actions.map((action, actionIndex) => (
                            <li key={`${action.person}-${actionIndex}`}>
                              {action.person}: {action.action}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </article>
                  ))}
                </div>
              </>
            ) : null}

            <h3>関連ノード</h3>
            <RelatedGraph result={result} />

            <h3>検索根拠</h3>
            <div className="evidenceList">
              {result.vector_results.map((item) => (
                <article className="evidence" key={item.id}>
                  <div>
                    <strong>{item.id}</strong>
                    <span>{item.source}</span>
                  </div>
                  <p>{item.content}</p>
                  <small>score: {item.score}</small>
                </article>
              ))}
            </div>

          </section>
        ) : null}
      </section>
    </main>
  );
}
