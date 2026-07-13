import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, RefreshCw } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { categoriesApi, dashboardApi, tasksApi } from "../services/api";
import { createDefaultSchedule, filterTasks, normalizeStatus, STATUS_FILTERS } from "./taskflow/taskflowHelpers";
import CategoryManager from "./taskflow/CategoryManager";
import TaskComposer from "./taskflow/TaskComposer";
import TaskFilters from "./taskflow/TaskFilters";
import TaskList from "./taskflow/TaskList";
import TaskMetrics from "./taskflow/TaskMetrics";
import "../styles/taskflow.css";

function TaskFlowPro() {
    const navigate = useNavigate();
    const { user, signOut } = useAuth();
    const [tasks, setTasks] = useState([]);
    const [categories, setCategories] = useState([]);
    const [summary, setSummary] = useState(null);
    const [filter, setFilter] = useState("all");
    const [taskForm, setTaskForm] = useState(() => ({
        title: "",
        description: "",
        category: "",
        priority: "Medium",
        ...createDefaultSchedule(),
    }));
    const [loading, setLoading] = useState(false);
    const [loadingTaskId, setLoadingTaskId] = useState(null);
    const [error, setError] = useState("");
    const [refreshing, setRefreshing] = useState(false);

    const loadBoard = useCallback(async () => {
        setRefreshing(true);
        setError("");

        try {
            const [tasksResponse, categoriesResponse, summaryResponse] = await Promise.all([
                tasksApi.list(),
                categoriesApi.list(),
                dashboardApi.summary(),
            ]);

            setTasks(tasksResponse.data);
            setCategories(categoriesResponse.data);
            setSummary(summaryResponse.data);

            if (!taskForm.category && categoriesResponse.data.length > 0) {
                setTaskForm((current) => ({
                    ...current,
                    category: String(categoriesResponse.data[0].id),
                }));
            }
        } catch (requestError) {
            setError(requestError.response?.data?.detail || requestError.response?.data?.message || "Unable to load tasks.");
        } finally {
            setRefreshing(false);
        }
    }, [taskForm.category]);

    useEffect(() => {
        const timeoutId = window.setTimeout(() => {
            void loadBoard();
        }, 0);

        return () => window.clearTimeout(timeoutId);
    }, [loadBoard]);

    const visibleTasks = useMemo(() => filterTasks(tasks, filter), [tasks, filter]);
    const completedCount = tasks.filter((task) => normalizeStatus(task.status) === "completed").length;
    const activeCount = tasks.filter((task) => normalizeStatus(task.status) === "in progress").length;

    async function handleCreateTask() {
        if (!taskForm.title.trim() || !taskForm.category) {
            setError("Add a title and choose a category before creating the task.");
            return;
        }

        setLoading(true);
        setError("");

        try {
            const payload = {
                title: taskForm.title.trim(),
                description: taskForm.description.trim(),
                category: Number(taskForm.category),
                priority: taskForm.priority,
                start_time: taskForm.start_time,
                end_time: taskForm.end_time,
            };

            const { data } = await tasksApi.create(payload);
            setTasks((current) => [...current, data]);
            setTaskForm((current) => ({
                ...current,
                title: "",
                description: "",
                ...createDefaultSchedule(),
            }));
            await loadBoard();
        } catch (requestError) {
            setError(
                requestError.response?.data?.detail ||
                    requestError.response?.data?.message ||
                    requestError.response?.data?.non_field_errors?.[0] ||
                    "Unable to create task."
            );
        } finally {
            setLoading(false);
        }
    }

    async function handleCreateCategory(name) {
        setLoading(true);
        setError("");

        try {
            const { data } = await categoriesApi.create({ name });
            setCategories((current) => [...current, data]);
            setTaskForm((current) => ({
                ...current,
                category: String(data.id),
            }));
        } catch (requestError) {
            setError(requestError.response?.data?.name?.[0] || requestError.response?.data?.detail || "Unable to create category.");
        } finally {
            setLoading(false);
        }
    }

    async function handleTaskAction(taskId, action) {
        setLoadingTaskId(taskId);
        setError("");

        try {
            switch (action) {
                case "start":
                    await tasksApi.start(taskId);
                    break;
                case "pause":
                    await tasksApi.pause(taskId);
                    break;
                case "resume":
                    await tasksApi.resume(taskId);
                    break;
                case "stop":
                    await tasksApi.stop(taskId);
                    break;
                case "complete":
                    await tasksApi.complete(taskId);
                    break;
                default:
                    break;
            }

            await loadBoard();
        } catch (requestError) {
            setError(requestError.response?.data?.message || requestError.response?.data?.error || "Unable to update task.");
        } finally {
            setLoadingTaskId(null);
        }
    }

    async function handleDeleteTask(taskId) {
        setLoadingTaskId(taskId);
        setError("");

        try {
            await tasksApi.remove(taskId);
            await loadBoard();
        } catch (requestError) {
            setError(requestError.response?.data?.detail || "Unable to delete task.");
        } finally {
            setLoadingTaskId(null);
        }
    }

    async function handleRescheduleTask(taskId, schedule) {
        setLoadingTaskId(taskId);
        setError("");

        try {
            await tasksApi.reschedule(taskId, schedule);
            await loadBoard();
        } catch (requestError) {
            setError(requestError.response?.data?.error || "Unable to reschedule task.");
        } finally {
            setLoadingTaskId(null);
        }
    }

    async function handleRefresh() {
        await loadBoard();
    }

    async function handleLogout() {
        await signOut();
        navigate("/", { replace: true });
    }

    return (
        <div className="taskflow-page">
            <div className="taskflow-shell">
                <header className="hero-card">
                    <div>
                        <p className="eyebrow">TaskFlow Pro</p>
                        <h1>Move work through a calmer, clearer flow.</h1>
                        <p className="hero-copy">
                            Build tasks, assign categories, and drive them through the backend lifecycle with live API calls.
                        </p>
                    </div>

                    <div className="hero-actions">
                        <span className="user-chip">{user?.first_name || user?.email || "Signed in"}</span>
                        <button type="button" className="secondary-button" onClick={handleRefresh} disabled={refreshing}>
                            <RefreshCw size={15} className={refreshing ? "spin" : ""} />
                            Refresh
                        </button>
                        <button type="button" className="secondary-button" onClick={handleLogout}>
                            <LogOut size={15} />
                            Logout
                        </button>
                    </div>
                </header>

                {error ? <div className="error-banner">{error}</div> : null}

                <TaskMetrics summary={summary} />

                <div className="taskflow-grid">
                    <div className="taskflow-main-column">
                        <TaskComposer
                            categories={categories}
                            form={taskForm}
                            onChange={setTaskForm}
                            onSubmit={handleCreateTask}
                            loading={loading}
                        />

                        <section className="panel-card">
                            <div className="panel-heading">
                                <div>
                                    <p className="eyebrow">Task board</p>
                                    <h2>{filter === "all" ? "All tasks" : `${filter} tasks`}</h2>
                                </div>
                                <span className="muted-count">{visibleTasks.length} visible</span>
                            </div>

                            <TaskFilters
                                filter={filter}
                                onFilterChange={setFilter}
                                completedCount={completedCount}
                                onClearCompleted={async () => {
                                    const completedTasks = tasks.filter((task) => normalizeStatus(task.status) === "completed");
                                    await Promise.all(completedTasks.map((task) => tasksApi.remove(task.id)));
                                    await loadBoard();
                                }}
                            />

                            <TaskList
                                tasks={visibleTasks}
                                categories={categories}
                                onAction={handleTaskAction}
                                onDelete={handleDeleteTask}
                                onReschedule={handleRescheduleTask}
                                loadingTaskId={loadingTaskId}
                            />
                        </section>
                    </div>

                    <div className="taskflow-side-column">
                        <CategoryManager categories={categories} onCreate={handleCreateCategory} loading={loading} />

                        <section className="panel-card status-panel">
                            <div className="panel-heading">
                                <div>
                                    <p className="eyebrow">Quick pulse</p>
                                    <h2>Current status</h2>
                                </div>
                            </div>

                            <div className="pulse-list">
                                <div>
                                    <span>Active tasks</span>
                                    <strong>{activeCount}</strong>
                                </div>
                                <div>
                                    <span>Completed</span>
                                    <strong>{completedCount}</strong>
                                </div>
                                <div>
                                    <span>Available filters</span>
                                    <strong>{STATUS_FILTERS.length}</strong>
                                </div>
                            </div>
                        </section>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default TaskFlowPro;