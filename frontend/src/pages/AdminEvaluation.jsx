import { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { toast } from 'sonner';
import {
  FlaskConical, Play, X, CheckCircle2, XCircle, Wrench, Route, ShieldCheck,
  LifeBuoy, Sparkles, Clock, Workflow, ListChecks,
} from 'lucide-react';
import { useTheme } from '@/context/ThemeContext';
import { evaluationApi, getErrorMessage } from '@/services/api';
import { cn } from '@/lib/utils';
import StatCard from '@/components/statcard';

const CATEGORY_LABELS = {
  task_visibility: 'Task Visibility',
  task_maintenance: 'Task Maintenance',
  user_management: 'User Mgmt',
  reminders: 'Reminders',
  analytics: 'Analytics',
  system_maintenance: 'System Maint.',
  permission: 'Permission',
  failure_injection: 'Failure Inj.',
  workflow: 'Workflow',
};

function pct(v) {
  return v === null || v === undefined ? '—' : `${v}%`;
}

function ms(v) {
  if (v === null || v === undefined) return '—';
  return v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`;
}

function formatDateTime(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleString('en', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function DimBadge({ label, value }) {
  if (value === null || value === undefined) return null;
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium',
      value ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400'
    )}>
      {value ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />} {label}
    </span>
  );
}

export default function AdminEvaluation() {
  const { isDark } = useTheme();
  const [summary, setSummary] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [selectedCase, setSelectedCase] = useState(null);

  const loadAll = useCallback(async () => {
    const [summaryRes, runsRes] = await Promise.all([evaluationApi.summary(), evaluationApi.runs()]);
    setSummary(summaryRes.data);
    setRuns(runsRes.data);
  }, []);

  useEffect(() => {
    loadAll().finally(() => setLoading(false));
  }, [loadAll]);

  const handleRun = async () => {
    setRunning(true);
    try {
      const { data } = await evaluationApi.trigger();
      toast.success(`Evaluation finished: ${data.passed_cases}/${data.total_cases} scenarios passed.`);
      await loadAll();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Evaluation run failed'));
    } finally {
      setRunning(false);
    }
  };

  const openRunDetail = async (runId) => {
    setRunDetailLoading(true);
    try {
      const { data } = await evaluationApi.runDetail(runId);
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

  const latest = summary?.latest;
  const m = latest?.metrics || {};

  const categoryData = Object.entries(m.cases_by_category || {}).map(([cat, counts]) => ({
    category: CATEGORY_LABELS[cat] || cat,
    passed: counts.passed,
    failed: counts.failed,
  }));

  const trendData = (summary?.trend || []).map((t) => ({
    label: formatDateTime(t.started_at),
    task_success_rate: t.task_success_rate,
  }));

  const chartGridColor = isDark ? '#1e293b' : '#f1f5f9';
  const chartTickColor = isDark ? '#64748b' : '#94a3b8';
  const chartTooltipStyle = {
    borderRadius: '12px',
    border: `1px solid ${isDark ? '#1e293b' : '#f1f5f9'}`,
    fontSize: '13px',
    background: isDark ? '#0f172a' : '#ffffff',
    color: isDark ? '#f1f5f9' : '#0f172a',
  };

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <FlaskConical className="w-6 h-6 text-indigo-600" /> Agent Evaluation
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Automated scenarios that measure how the Admin Copilot actually behaves -- tool use, planning, permissions, hallucinations, and failure recovery.
          </p>
        </div>
        <button
          onClick={handleRun}
          disabled={running}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50 shrink-0"
        >
          <Play className="w-4 h-4" /> {running ? 'Running suite (this can take ~1 min)...' : 'Run Evaluation'}
        </button>
      </div>

      {!latest ? (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-10 text-center">
          <p className="text-sm text-slate-400">No evaluation runs yet. Click "Run Evaluation" to grade the copilot against ~20 realistic admin scenarios.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <StatCard icon={ListChecks} label="Total Scenarios" value={latest.total_cases} color="bg-slate-500" />
            <StatCard icon={CheckCircle2} label="Passed" value={latest.passed_cases} color="bg-emerald-500" />
            <StatCard icon={XCircle} label="Failed" value={latest.failed_cases} color="bg-red-500" />
            <StatCard icon={Clock} label="Run Duration" value={ms(latest.duration_ms)} color="bg-slate-500" />
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatCard icon={CheckCircle2} label="Task Success Rate" value={pct(m.task_success_rate)} color="bg-indigo-500" />
            <StatCard icon={Wrench} label="Tool Selection Accuracy" value={pct(m.tool_selection_accuracy)} color="bg-blue-500" />
            <StatCard icon={Route} label="Planning Accuracy" value={pct(m.planning_accuracy)} color="bg-purple-500" />
            <StatCard icon={ShieldCheck} label="Permission Accuracy" value={pct(m.permission_accuracy)} color="bg-teal-500" />
            <StatCard icon={LifeBuoy} label="Error Recovery Rate" value={pct(m.error_recovery_rate)} color="bg-cyan-500" />
            <StatCard icon={Sparkles} label="Hallucination Rate" value={pct(m.hallucination_rate)} color="bg-amber-500" subtitle="Lower is better" />
            <StatCard icon={Clock} label="Avg Response Time" value={ms(m.avg_response_time_ms)} color="bg-slate-500" />
            <StatCard icon={Workflow} label="Workflow Completion" value={pct(m.workflow_completion_rate)} color="bg-pink-500" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Latest Run: Pass/Fail by Category</h2>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={categoryData} margin={{ left: -16, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} vertical={false} />
                  <XAxis dataKey="category" tick={{ fill: chartTickColor, fontSize: 11 }} axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={50} />
                  <YAxis allowDecimals={false} tick={{ fill: chartTickColor, fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={chartTooltipStyle} cursor={{ fill: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)' }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="passed" stackId="a" fill="#10b981" radius={[0, 0, 0, 0]} maxBarSize={28} />
                  <Bar dataKey="failed" stackId="a" fill="#ef4444" radius={[4, 4, 0, 0]} maxBarSize={28} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Task Success Rate Trend</h2>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={trendData} margin={{ left: -16, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: chartTickColor, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fill: chartTickColor, fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={chartTooltipStyle} formatter={(v) => [`${v}%`, 'Task Success Rate']} />
                  <Line type="monotone" dataKey="task_success_rate" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      {/* Run history */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 dark:border-slate-800">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Run History</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide border-b border-slate-100 dark:border-slate-800">
                <th className="px-4 py-3 font-medium">Run</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Passed</th>
                <th className="px-4 py-3 font-medium">Task Success Rate</th>
                <th className="px-4 py-3 font-medium">Duration</th>
                <th className="px-4 py-3 font-medium">Triggered By</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">No runs yet.</td></tr>
              ) : (
                runs.map((run) => (
                  <tr
                    key={run.id}
                    onClick={() => openRunDetail(run.id)}
                    className="border-b border-slate-50 dark:border-slate-800/60 last:border-0 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  >
                    <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">#{run.id} · {formatDateTime(run.started_at)}</td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        'px-2 py-0.5 rounded-full text-[11px] font-medium',
                        run.status === 'completed' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400'
                      )}>
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{run.passed_cases}/{run.total_cases}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{pct(run.metrics?.task_success_rate)}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{ms(run.duration_ms)}</td>
                    <td className="px-4 py-3 text-slate-400">{run.triggered_by_email || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Run detail modal -- list of case results */}
      {(selectedRun || runDetailLoading) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30" onClick={() => setSelectedRun(null)}>
          <div
            className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-xl w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-slate-100 dark:border-slate-800">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                {selectedRun ? `Run #${selectedRun.id} -- ${selectedRun.passed_cases}/${selectedRun.total_cases} passed` : 'Loading...'}
              </h3>
              <button onClick={() => setSelectedRun(null)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="overflow-y-auto p-5 space-y-2">
              {runDetailLoading || !selectedRun ? (
                <div className="flex justify-center py-10">
                  <div className="w-6 h-6 border-4 border-slate-200 dark:border-slate-800 border-t-indigo-600 rounded-full animate-spin" />
                </div>
              ) : (
                selectedRun.case_results.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setSelectedCase(c)}
                    className="w-full text-left p-3 rounded-xl border border-slate-100 dark:border-slate-800 hover:border-indigo-200 dark:hover:border-indigo-500/30 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{c.scenario_name}</p>
                      <span className={cn(
                        'px-2 py-0.5 rounded-full text-[11px] font-medium shrink-0',
                        c.passed ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400'
                      )}>
                        {c.passed ? 'PASS' : 'FAIL'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{CATEGORY_LABELS[c.category] || c.category} · {ms(c.response_time_ms)}</p>
                    {!c.passed && c.failure_reason && <p className="text-xs text-red-500 dark:text-red-400 mt-1 truncate">{c.failure_reason}</p>}
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Single case detail modal */}
      {selectedCase && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/30" onClick={() => setSelectedCase(null)}>
          <div
            className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-slate-100 dark:border-slate-800">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-slate-100">{selectedCase.scenario_name}</h3>
                <p className="text-xs text-slate-400 mt-0.5">{CATEGORY_LABELS[selectedCase.category] || selectedCase.category}</p>
              </div>
              <button onClick={() => setSelectedCase(null)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="overflow-y-auto p-5 space-y-4">
              <div className="flex flex-wrap gap-2">
                <DimBadge label="Tool Selection" value={selectedCase.tool_selection_correct} />
                <DimBadge label="Planning" value={selectedCase.planning_correct} />
                <DimBadge label="Permission" value={selectedCase.permission_correct} />
                <DimBadge label={selectedCase.hallucination_detected ? 'Hallucinated' : 'No Hallucination'} value={selectedCase.hallucination_detected === null ? null : !selectedCase.hallucination_detected} />
                <DimBadge label="Recovered" value={selectedCase.error_recovered} />
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Trigger</p>
                <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{selectedCase.trigger_description}</p>
              </div>
              {!selectedCase.passed && (
                <div>
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Why it failed</p>
                  <p className="text-sm text-red-600 dark:text-red-400">{selectedCase.failure_reason || 'No reason recorded.'}</p>
                </div>
              )}
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Expected</p>
                <pre className="text-xs bg-slate-50 dark:bg-slate-800/60 rounded-lg p-3 overflow-x-auto text-slate-700 dark:text-slate-300">{JSON.stringify(selectedCase.expected, null, 2)}</pre>
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Actual</p>
                <pre className="text-xs bg-slate-50 dark:bg-slate-800/60 rounded-lg p-3 overflow-x-auto text-slate-700 dark:text-slate-300">{JSON.stringify(selectedCase.actual, null, 2)}</pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
