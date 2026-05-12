export type AnalysisRequest = {
  target_market: string;
  assets: string;
  idea_detail: string;
};

export type AnalysisResponse = {
  analysis_id: string;
  status: string;
  summary: string;
  vector_results: Array<{
    id: string;
    content: string;
    score: number;
    source: string;
  }>;
  graph_results: Array<{
    id: string;
    label: string;
    type: string;
    relation: string;
  }>;
  graph_view: {
    nodes: Array<{
      id: string;
      label: string;
      type: string;
      source: string;
    }>;
    edges: Array<{
      source_id: string;
      target_id: string;
      relation: string;
    }>;
  };
  context: {
    external_context: string;
    internal_context: string;
    org_context: string;
  };
  llm_analysis: {
    stage1: Record<string, { score?: string; reason?: string; key_points?: string[] }>;
    stage2: {
      proposals?: Array<{
        title?: string;
        summary?: string;
        timing_score?: string;
        timing_reason?: string;
        tech_fit_score?: string;
        tech_fit_reason?: string;
        bottleneck?: string;
        bottleneck_solution?: string;
        next_actions?: Array<{ person?: string; action?: string }>;
      }>;
      approver_summary?: string;
      tier2?: Record<string, unknown>;
    };
    go_no_verdict: string;
    approver_summary: string;
  } | null;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function createAnalysis(
  payload: AnalysisRequest,
): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/analyses`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json();
}
