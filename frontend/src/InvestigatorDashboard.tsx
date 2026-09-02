import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import ForceGraph2D from 'react-force-graph-2d';
import {
  ArrowLeft,
  ShieldAlert,
  Network,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Loader2,
  Search,
  X,
  Layers,
  Users,
  DollarSign,
  Eye,
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

/* ── Types ── */
interface CaseItem {
  id: number;
  account_id: string;
  pattern_type: string;
  cluster_id: string;
  risk_score: number;
  risk_bucket: string;
  evidence_summary: string;
  status: string;
  created_at: string;
  upi_id: string;
}

interface Cluster {
  cluster_id: string;
  highest_risk_score: number;
  highest_risk_bucket: string;
  account_count: number;
  total_transaction_amount: number;
  cases: CaseItem[];
}

interface TraceNode {
  account_id: string;
  upi_id: string;
  account_type: string;
  account_age_days: number;
}

interface TraceEdge {
  transaction_id: string;
  sender_id: string;
  receiver_id: string;
  amount: number;
  timestamp: string;
  pattern_type: string;
  cluster_id: string;
}

interface TraceResponse {
  center_account_id: string;
  center_upi_id: string;
  hops: number;
  nodes: TraceNode[];
  edges: TraceEdge[];
}

/* ── Helpers ── */
const bucketColor: Record<string, string> = {
  Critical: 'bg-rose-500 text-white',
  High: 'bg-amber-500 text-slate-950',
  Medium: 'bg-yellow-400 text-slate-950',
  Low: 'bg-emerald-500 text-white',
};

const bucketBorder: Record<string, string> = {
  Critical: 'border-rose-500/50',
  High: 'border-amber-500/50',
  Medium: 'border-yellow-400/50',
  Low: 'border-emerald-500/50',
};

const nodeColor: Record<string, string> = {
  personal: '#60a5fa',   // blue-400
  merchant: '#a78bfa',   // purple-400
  payroll: '#2dd4bf',    // teal-400
};

const fmt = (n: number) =>
  '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 2 });

/* ── Main Component ── */
export default function InvestigatorDashboard() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Detail screen state
  const [selectedCluster, setSelectedCluster] = useState<Cluster | null>(null);
  const [traceData, setTraceData] = useState<TraceResponse | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<TraceNode | null>(null);

  // Case action states  — maps case id → updated status
  const [caseStatuses, setCaseStatuses] = useState<Record<number, string>>({});

  /* ── Fetch clusters ── */
  const fetchClusters = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await axios.get<Cluster[]>(`${API_BASE}/networks`);
      setClusters(res.data);
    } catch (e: any) {
      setError(e.message || 'Failed to fetch networks.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchClusters();
  }, [fetchClusters]);

  /* ── Open cluster detail ── */
  const openCluster = async (cluster: Cluster) => {
    setSelectedCluster(cluster);
    setSelectedNode(null);
    setTraceLoading(true);

    // Pick the primary account from the top case
    const primaryAccount = cluster.cases[0]?.account_id;
    if (!primaryAccount) {
      setTraceLoading(false);
      return;
    }

    try {
      const res = await axios.get<TraceResponse>(
        `${API_BASE}/trace/${primaryAccount}?hops=2`
      );
      setTraceData(res.data);
    } catch (e: any) {
      console.error('Trace fetch error:', e);
      setTraceData(null);
    } finally {
      setTraceLoading(false);
    }
  };

  /* ── Case action handler ── */
  const handleCaseAction = async (
    caseId: number,
    action: 'mark_legitimate' | 'escalate'
  ) => {
    // Optimistic update
    setCaseStatuses((prev) => ({
      ...prev,
      [caseId]: action === 'mark_legitimate' ? 'reviewed_legitimate' : 'escalated',
    }));

    try {
      await axios.post(`${API_BASE}/cases/${caseId}/action`, { action });
    } catch (e: any) {
      console.error('Case action failed:', e);
      // Revert on error
      setCaseStatuses((prev) => {
        const copy = { ...prev };
        delete copy[caseId];
        return copy;
      });
    }
  };

  /* ── Determine effective case status ── */
  const effectiveStatus = (c: CaseItem): string =>
    caseStatuses[c.id] ?? c.status;

  /* ── Force-graph data transform ── */
  const graphData = React.useMemo(() => {
    if (!traceData) return { nodes: [], links: [] };

    // Count how many cases reference each account
    const caseCounts: Record<string, number> = {};
    if (selectedCluster) {
      for (const c of selectedCluster.cases) {
        caseCounts[c.account_id] = (caseCounts[c.account_id] || 0) + 1;
      }
    }

    const nodes = traceData.nodes.map((n) => ({
      id: n.account_id,
      label: n.upi_id || n.account_id.slice(0, 8),
      type: n.account_type,
      color: nodeColor[n.account_type] || '#94a3b8',
      val: caseCounts[n.account_id] && caseCounts[n.account_id] > 1 ? 6 : 3,
      ...n,
    }));

    const links = traceData.edges.map((e) => ({
      source: e.sender_id,
      target: e.receiver_id,
      amount: e.amount,
      timestamp: e.timestamp,
      pattern_type: e.pattern_type,
      cluster_id: e.cluster_id,
    }));

    return { nodes, links };
  }, [traceData, selectedCluster]);

  /* ── Graph container ref for sizing ── */
  const graphContainerRef = useRef<HTMLDivElement>(null);
  const [graphDims, setGraphDims] = useState({ width: 600, height: 340 });

  useEffect(() => {
    if (!graphContainerRef.current) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setGraphDims({
          width: entry.contentRect.width,
          height: Math.max(entry.contentRect.height, 300),
        });
      }
    });
    obs.observe(graphContainerRef.current);
    return () => obs.disconnect();
  }, [selectedCluster]);

  /* ─────────────────────────  RENDER  ───────────────────────── */

  // ── Screen 2: Network Detail ──
  if (selectedCluster) {
    return (
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {/* Detail Header */}
        <div className="shrink-0 px-6 py-4 border-b border-slate-800 bg-slate-900/80 backdrop-blur flex items-center gap-4">
          <button
            onClick={() => {
              setSelectedCluster(null);
              setTraceData(null);
              setSelectedNode(null);
            }}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors cursor-pointer"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h2 className="font-bold text-base text-slate-100 font-mono">
                {selectedCluster.cluster_id}
              </h2>
              <span
                className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wide ${
                  bucketColor[selectedCluster.highest_risk_bucket] || 'bg-slate-600 text-slate-200'
                }`}
              >
                {selectedCluster.highest_risk_bucket}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              {selectedCluster.account_count} accounts · {fmt(selectedCluster.total_transaction_amount)} total volume ·{' '}
              {selectedCluster.cases.length} case{selectedCluster.cases.length !== 1 ? 's' : ''}
            </p>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Force Graph Card */}
          <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800/60 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Network size={16} className="text-indigo-400" />
                <span className="text-xs font-semibold text-slate-300">Transaction Graph (2-hop)</span>
              </div>
              {/* Legend */}
              <div className="flex items-center gap-3">
                {Object.entries(nodeColor).map(([type, color]) => (
                  <div key={type} className="flex items-center gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                    <span className="text-[10px] text-slate-400 capitalize">{type}</span>
                  </div>
                ))}
              </div>
            </div>

            <div
              ref={graphContainerRef}
              className="relative bg-slate-950/60"
              style={{ height: 340 }}
            >
              {traceLoading ? (
                <div className="absolute inset-0 flex items-center justify-center">
                  <Loader2 size={28} className="animate-spin text-indigo-400" />
                </div>
              ) : graphData.nodes.length > 0 ? (
                <ForceGraph2D
                  width={graphDims.width}
                  height={340}
                  graphData={graphData}
                  nodeLabel={(node: any) => `${node.label} (${node.type})`}
                  nodeColor={(node: any) => node.color}
                  nodeRelSize={5}
                  nodeVal={(node: any) => node.val}
                  linkDirectionalArrowLength={4}
                  linkDirectionalArrowRelPos={0.85}
                  linkColor={() => 'rgba(100,116,139,0.4)'}
                  linkWidth={1.5}
                  linkLabel={(link: any) =>
                    `₹${link.amount?.toLocaleString('en-IN')} · ${new Date(link.timestamp).toLocaleString()}`
                  }
                  onNodeClick={(node: any) => {
                    const tn = traceData?.nodes.find((n) => n.account_id === node.id);
                    setSelectedNode(tn || null);
                  }}
                  backgroundColor="transparent"
                  cooldownTicks={80}
                  nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
                    const size = node.val * 1.6;
                    // Glow
                    ctx.beginPath();
                    ctx.arc(node.x, node.y, size + 2, 0, 2 * Math.PI);
                    ctx.fillStyle = node.color + '22';
                    ctx.fill();
                    // Circle
                    ctx.beginPath();
                    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
                    ctx.fillStyle = node.color;
                    ctx.fill();
                    ctx.strokeStyle = 'rgba(15,23,42,0.6)';
                    ctx.lineWidth = 1;
                    ctx.stroke();
                    // Label
                    if (globalScale > 0.8) {
                      const label = node.label.length > 16 ? node.label.slice(0, 14) + '…' : node.label;
                      const fontSize = Math.max(10 / globalScale, 3);
                      ctx.font = `600 ${fontSize}px Inter, system-ui, sans-serif`;
                      ctx.textAlign = 'center';
                      ctx.textBaseline = 'top';
                      ctx.fillStyle = '#e2e8f0';
                      ctx.fillText(label, node.x, node.y + size + 3);
                    }
                  }}
                />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-xs">
                  No graph data available.
                </div>
              )}

              {/* Selected Node Side Panel */}
              {selectedNode && (
                <div className="absolute top-3 right-3 w-56 bg-slate-900/95 backdrop-blur border border-slate-700 rounded-xl p-3 shadow-xl z-20 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Account Details</span>
                    <button
                      onClick={() => setSelectedNode(null)}
                      className="p-0.5 rounded hover:bg-slate-700 text-slate-500 hover:text-white transition-colors cursor-pointer"
                    >
                      <X size={14} />
                    </button>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span className="text-slate-400">UPI ID:</span>
                      <span className="text-slate-200 font-mono text-[11px] max-w-[140px] truncate">
                        {selectedNode.upi_id || '—'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Type:</span>
                      <span className="text-slate-200 capitalize">{selectedNode.account_type}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Account Age:</span>
                      <span className={`font-semibold ${selectedNode.account_age_days < 30 ? 'text-amber-400' : 'text-slate-200'}`}>
                        {selectedNode.account_age_days}d
                        {selectedNode.account_age_days < 30 && (
                          <span className="ml-1 text-[9px] bg-amber-500/20 text-amber-300 px-1 rounded">NEW</span>
                        )}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Case Evidence List */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Eye size={14} className="text-indigo-400" />
              Case Evidence ({selectedCluster.cases.length})
            </h3>

            {selectedCluster.cases.map((c) => {
              const status = effectiveStatus(c);
              const isActioned = status !== 'open';

              return (
                <div
                  key={c.id}
                  className={`bg-slate-900 rounded-xl border p-4 space-y-3 transition-all ${
                    isActioned
                      ? status === 'reviewed_legitimate'
                        ? 'border-emerald-500/30 opacity-75'
                        : 'border-rose-500/30 opacity-75'
                      : `${bucketBorder[c.risk_bucket] || 'border-slate-800'}`
                  }`}
                >
                  {/* Case header */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] font-mono text-slate-400">Case #{c.id}</span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                            bucketColor[c.risk_bucket] || 'bg-slate-600 text-slate-200'
                          }`}
                        >
                          {c.risk_bucket}
                        </span>
                        <span className="text-[10px] bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-500/30 font-medium">
                          {c.pattern_type}
                        </span>
                        {isActioned && (
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                              status === 'reviewed_legitimate'
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                            }`}
                          >
                            {status === 'reviewed_legitimate' ? '✓ Legitimate' : '⚑ Escalated'}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] font-mono text-slate-400 mt-1 truncate">
                        {c.upi_id || c.account_id.slice(0, 16) + '…'}
                      </p>
                    </div>
                    <span className="text-xs font-bold text-slate-300 whitespace-nowrap">
                      Score: {c.risk_score.toFixed(1)}
                    </span>
                  </div>

                  {/* Evidence */}
                  <p
                    className={`text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-3 rounded-lg border border-slate-800/60 ${
                      isActioned ? 'line-through decoration-slate-600' : ''
                    }`}
                  >
                    "{c.evidence_summary}"
                  </p>

                  {/* Action buttons */}
                  {!isActioned && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleCaseAction(c.id, 'mark_legitimate')}
                        className="flex-1 flex items-center justify-center gap-1.5 text-[11px] font-semibold py-2 px-3 rounded-lg bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/20 transition-colors cursor-pointer"
                      >
                        <CheckCircle2 size={13} />
                        Mark Legitimate
                      </button>
                      <button
                        onClick={() => handleCaseAction(c.id, 'escalate')}
                        className="flex-1 flex items-center justify-center gap-1.5 text-[11px] font-semibold py-2 px-3 rounded-lg bg-rose-500/10 text-rose-300 border border-rose-500/30 hover:bg-rose-500/20 transition-colors cursor-pointer"
                      >
                        <AlertTriangle size={13} />
                        Escalate
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ── Screen 1: Network List ──
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      {/* List Header */}
      <div className="shrink-0 px-6 py-4 border-b border-slate-800 bg-slate-900/80 backdrop-blur">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-500/20 text-indigo-400">
              <Layers size={18} />
            </div>
            <div>
              <h2 className="font-bold text-base text-slate-100">Fraud Networks</h2>
              <p className="text-[11px] text-slate-400">
                {clusters.length} active cluster{clusters.length !== 1 ? 's' : ''} detected
              </p>
            </div>
          </div>
          <button
            onClick={fetchClusters}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors cursor-pointer"
            title="Refresh"
          >
            <Search size={16} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={28} className="animate-spin text-indigo-400" />
          </div>
        ) : error ? (
          <div className="text-center py-20 space-y-2">
            <ShieldAlert size={32} className="text-rose-400 mx-auto" />
            <p className="text-xs text-slate-400">{error}</p>
            <button
              onClick={fetchClusters}
              className="text-xs text-indigo-400 underline cursor-pointer"
            >
              Retry
            </button>
          </div>
        ) : clusters.length === 0 ? (
          <div className="text-center py-20 space-y-2">
            <CheckCircle2 size={32} className="text-emerald-400 mx-auto" />
            <p className="text-sm text-slate-300 font-semibold">All Clear</p>
            <p className="text-xs text-slate-500">No open fraud networks detected.</p>
          </div>
        ) : (
          clusters.map((cluster) => (
            <button
              key={cluster.cluster_id}
              onClick={() => openCluster(cluster)}
              className="w-full text-left bg-slate-900 hover:bg-slate-800/80 rounded-xl border border-slate-800 hover:border-slate-700 p-4 transition-all cursor-pointer group"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0 space-y-2">
                  {/* Top row: cluster ID + badge */}
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="font-mono text-sm font-bold text-slate-100 truncate">
                      {cluster.cluster_id}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wide ${
                        bucketColor[cluster.highest_risk_bucket] || 'bg-slate-600 text-slate-200'
                      }`}
                    >
                      {cluster.highest_risk_bucket}
                    </span>
                  </div>

                  {/* Stats row */}
                  <div className="flex items-center gap-4 text-[11px] text-slate-400">
                    <span className="flex items-center gap-1">
                      <Users size={12} />
                      {cluster.account_count} accounts
                    </span>
                    <span className="flex items-center gap-1">
                      <DollarSign size={12} />
                      {fmt(cluster.total_transaction_amount)}
                    </span>
                  </div>

                  {/* Corroborating signals */}
                  {cluster.cases.length > 1 && (
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                      <span className="text-[10px] font-medium text-amber-300">
                        {cluster.cases.length} signals agree
                      </span>
                    </div>
                  )}
                </div>

                {/* Arrow */}
                <ChevronRight
                  size={18}
                  className="text-slate-600 group-hover:text-slate-300 transition-colors shrink-0 mt-1"
                />
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
