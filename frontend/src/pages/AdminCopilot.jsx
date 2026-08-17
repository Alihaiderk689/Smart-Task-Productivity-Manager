import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import {
  Bot, Play, X, AlertTriangle, ListChecks, XCircle, Sparkles, Clock,
  Check, Ban, Loader2,
} from 'lucide-react';
import { copilotApi, getErrorMessage } from '@/services/api';
import { cn } from '@/lib/utils';
import StatCard from '@/components/statcard';
import CopilotQueryBox from '@/components/CopilotQueryBox';
import PageControls from '@/components/PageControls';

const CHAT_SESSION_ID = 'default';
// Both lists are fetched in full (capped at 50 server-side, see
// copilot/views.py::RecommendationListView/AgentRunListView) and paged
// client-side, since 50 items is small enough that a second round-trip per
// page would just add latency for no real benefit.
const PAGE_SIZE = 5;

const RISK_BADGE = {
  low: 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300',
  medium: 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400',
  high: 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400',
};

const STATUS_BADGE = {
  completed: 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  running: 'bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400',
  failed: 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400',
};

function formatDateTime(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleString('en', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export default function AdminCopilot() {
  const [summary, setSummary] = useState(null);
  const [agents, setAgents] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningAgent, setRunningAgent] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [resolvingId, setResolvingId] = useState(null);
  const [recPage, setRecPage] = useState(1);
  const [runsPage, setRunsPage] = useState(1);

  const loadAll = useCallback(async () => {
    const [summaryRes, agentsRes, recsRes, runsRes] = await Promise.all([
      copilotApi.dashboardSummary(),
      copilotApi.agentStatus(),
      copilotApi.recommendations({ status: 'pending' }),
      copilotApi.runs(),
    ]);
    setSummary(summaryRes.data);
    setAgents(agentsRes.data);
    setRecommendations(recsRes.data);
    setRuns(runsRes.data);
    // Resolving/approving a recommendation or running an agent can shrink
    // either list enough that the page we were on no longer exists --
    // simplest correct behavior is to just snap back to page 1 on any
    // reload rather than trying to preserve a now-possibly-invalid page.
    setRecPage(1);
    setRunsPage(1);
  }, []);

  useEffect(() => {
    loadAll().finally(() => setLoading(false));
  }, [loadAll]);

  const handleResolveRecommendation = async (rec, action) => {
    setResolvingId(rec.id);
    try {
      const call = action === 'approve' ? copilotApi.approveRecommendation : copilotApi.rejectRecommendation;
      const { data } = await call(rec.id);
      toast.success(
        action === 'approve'
          ? (data.status === 'executed' ? `Executed: ${rec.title}` : data.status === 'failed' ? `Approved but execution failed: ${rec.title}` : `Approved: ${rec.title}`)
          : `Dismissed: ${rec.title}`
      );
      await loadAll();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to update recommendation'));
    } finally {
      setResolvingId(null);
    }
  };

  const handleRunAgent = async (agentName) => {
    setRunningAgent(agentName);
    try {
      const { data } = await copilotApi.runAgent(agentName);
      toast[data.status === 'completed' ? 'success' : 'error'](
        data.status === 'completed' ? `${agentName} finished: ${data.result_summary}` : `${agentName} failed: ${data.error}`
      );
      await loadAll();
    } catch (err) {
      toast.error(err.response?.data?.error || `Failed to run ${agentName}`);
    } finally {
      setRunningAgent(null);
    }
  };

  const openRunDetail = async (run) => {
    setRunDetailLoading(true);
    try {
      const { data } = await copilotApi.runDetail(run.id);
      setSelectedRun(data);
    } catch {
      toast.error('Failed to load run detail');
    } finally {
      setRunDetailLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-slate-200 dark:border-slate-800 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  const recTotalPages = Math.max(1, Math.ceil(recommendations.length / PAGE_SIZE));
  const pagedRecommendations = recommendations.slice((recPage - 1) * PAGE_SIZE, recPage * PAGE_SIZE);
  const runsTotalPages = Math.max(1, Math.ceil(runs.length / PAGE_SIZE));
  const pagedRuns = runs.slice((runsPage - 1) * PAGE_SIZE, runsPage * PAGE_SIZE);

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
          <Bot className="w-6 h-6 text-indigo-600" /> Admin Copilot
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Autonomous agents that observe, reason, and report on the state of your app.
        </p>
      </div>

      {!summary.llm_configured && (
        <div className="flex items-start gap-3 p-4 rounded-2xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 mb-6">
          <Sparkles className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <p className="text-sm text-amber-800 dark:text-amber-300">
            No <code className="font-mono">GROQ_API_KEY</code> configured yet -- agents still run their deterministic checks
            and raise alerts normally, but summaries are template-based rather than LLM-written. Add a key to{' '}
            <code className="font-mono">backend/.env</code> to enable AI-generated reasoning.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard icon={ListChecks} label="Runs Today" value={summary.runs_today} color="bg-indigo-500" />
        <StatCard icon={XCircle} label="Failed Today" value={summary.runs_failed_today} color="bg-red-500" />
        <StatCard icon={AlertTriangle} label="Pending Recommendations" value={summary.pending_recommendations} color="bg-amber-500" />
        <StatCard icon={Bot} label="Agents Registered" value={summary.agents_registered.length} color="bg-purple-500" />
      </div>

      {/* Agents */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-5 mb-6">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Agents</h2>
        <div className="space-y-3">
          {agents.map((agent) => (
            <div key={agent.name} className="flex items-center justify-between gap-4 p-3 rounded-xl border border-slate-100 dark:border-slate-800">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-900 dark:text-slate-100 capitalize">{agent.name.replace(/_/g, ' ')}</p>
                <p className="text-xs text-slate-400 truncate">{agent.description}</p>
                {agent.last_run ? (
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className={cn('px-2 py-0.5 rounded-full text-[11px] font-medium', STATUS_BADGE[agent.last_run.status])}>
                      {agent.last_run.status}
                    </span>
                    <span className="text-[11px] text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {formatDateTime(agent.last_run.started_at)}
                    </span>
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-400 mt-1.5">Never run yet</p>
                )}
              </div>
              <button
                onClick={() => handleRunAgent(agent.name)}
                disabled={runningAgent === agent.name}
                className="shrink-0 flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5" /> {runningAgent === agent.name ? 'Running...' : 'Run Now'}
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recommendations */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Pending Recommendations</h2>
          {recommendations.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">No pending recommendations. All clear.</p>
          ) : (
            <div className="space-y-2">
              {pagedRecommendations.map((rec) => (
                <div key={rec.id} className="p-3 rounded-xl border border-slate-100 dark:border-slate-800">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{rec.title}</p>
                    <span className={cn('px-2 py-0.5 rounded-full text-[11px] font-medium shrink-0', RISK_BADGE[rec.risk])}>{rec.risk}</span>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{rec.description}</p>
                  {rec.impact && <p className="text-xs text-slate-400 mt-1"><span className="font-medium">Impact:</span> {rec.impact}</p>}
                  {rec.action_payload?.tool && (
                    <p className="text-[11px] font-mono text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/60 rounded-lg px-2 py-1 mt-2 break-all">
                      Will run: {rec.action_payload.tool}({JSON.stringify(rec.action_payload.input || {})})
                    </p>
                  )}
                  <div className="flex items-center gap-2 mt-3">
                    {rec.requires_approval ? (
                      <>
                        <button
                          onClick={() => handleResolveRecommendation(rec, 'approve')}
                          disabled={resolvingId === rec.id}
                          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors disabled:opacity-50"
                        >
                          {resolvingId === rec.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Approve
                        </button>
                        <button
                          onClick={() => handleResolveRecommendation(rec, 'reject')}
                          disabled={resolvingId === rec.id}
                          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors disabled:opacity-50"
                        >
                          <Ban className="w-3.5 h-3.5" /> Reject
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => handleResolveRecommendation(rec, 'reject')}
                        disabled={resolvingId === rec.id}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors disabled:opacity-50"
                      >
                        {resolvingId === rec.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />} Dismiss
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <PageControls page={recPage} totalPages={recTotalPages} onChange={setRecPage} />
        </div>

        {/* Recent runs / timeline */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Recent Actions</h2>
          {runs.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">No runs yet -- click "Run Now" on an agent above.</p>
          ) : (
            <div className="space-y-2">
              {pagedRuns.map((run) => (
                <button
                  key={run.id}
                  onClick={() => openRunDetail(run)}
                  className="w-full text-left p-3 rounded-xl border border-slate-100 dark:border-slate-800 hover:border-indigo-200 dark:hover:border-indigo-500/30 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100 capitalize">{run.agent_name.replace(/_/g, ' ')}</p>
                    <span className={cn('px-2 py-0.5 rounded-full text-[11px] font-medium shrink-0', STATUS_BADGE[run.status])}>{run.status}</span>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 truncate">{run.result_summary || run.error}</p>
                  <p className="text-[11px] text-slate-400 mt-1">{formatDateTime(run.started_at)} · {run.trigger}{run.confidence != null ? ` · ${Math.round(run.confidence * 100)}% confidence` : ''}</p>
                </button>
              ))}
            </div>
          )}
          <PageControls page={runsPage} totalPages={runsTotalPages} onChange={setRunsPage} />
        </div>
      </div>

      {/* Chat */}
      <CopilotQueryBox sessionId={CHAT_SESSION_ID} onProposed={loadAll} className="mt-6" />

      {/* Run detail modal */}
      {(selectedRun || runDetailLoading) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30" onClick={() => setSelectedRun(null)}>
          <div
            className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-xl w-full max-w-lg max-h-[80vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-slate-100 dark:border-slate-800">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100 capitalize">
                {selectedRun ? selectedRun.agent_name.replace(/_/g, ' ') : 'Loading...'}
              </h3>
              <button onClick={() => setSelectedRun(null)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="overflow-y-auto p-5 space-y-4">
              {runDetailLoading || !selectedRun ? (
                <div className="flex justify-center py-10">
                  <div className="w-6 h-6 border-4 border-slate-200 dark:border-slate-800 border-t-indigo-600 rounded-full animate-spin" />
                </div>
              ) : (
                <>
                  <div>
                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Reasoning</p>
                    <p className="text-sm text-slate-700 dark:text-slate-300">{selectedRun.reasoning_summary || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Result</p>
                    <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{selectedRun.result_summary || selectedRun.error || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Tool Calls</p>
                    <div className="space-y-2">
                      {selectedRun.tool_calls.map((tc) => (
                        <div key={tc.id} className="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 text-xs">
                          <span className="font-mono text-slate-700 dark:text-slate-300">{tc.tool_name}</span>
                          <span className={cn('font-medium', tc.success ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                            {tc.success ? 'ok' : 'failed'} · {tc.duration_ms}ms
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
