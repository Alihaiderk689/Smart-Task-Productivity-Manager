import axios from "axios";

export const API_ROOT = import.meta.env.VITE_API_ROOT || "/api";

const ACCESS_TOKEN_KEY = "smart-task-access-token";
const REFRESH_TOKEN_KEY = "smart-task-refresh-token";
const USER_KEY = "smart-task-user";

const authClient = axios.create({
	baseURL: API_ROOT,
});

const apiClient = axios.create({
	baseURL: API_ROOT,
});

export function getErrorMessage(err, fallback) {
	const data = err.response?.data;

	// A non-JSON error body (an HTML 500 page, a proxy's plaintext error,
	// etc.) is a string here, not an object. Without this check,
	// Object.values() below would treat it as an array of individual
	// characters and join them all back into a garbled "message".
	if (!data || typeof data !== "object") {
		return err.message || fallback;
	}

	if (typeof data.detail === "string") {
		return data.detail;
	}

	const messages = Object.values(data).flat().filter((value) => typeof value === "string");

	if (messages.length > 0) {
		return messages.join(" ");
	}

	return err.message || fallback;
}

// Maps a DRF field-keyed error response (e.g. {"email": ["This email is
// already registered."]}) to { email: "This email is already registered." }
// so a form can highlight the specific field instead of only showing one
// generic banner. Returns {} for non-field errors (a "detail" string, a
// non-JSON body, etc.) -- callers should fall back to getErrorMessage then.
export function getFieldErrors(err) {
	const data = err.response?.data;

	if (!data || typeof data !== "object" || typeof data.detail === "string") {
		return {};
	}

	const fieldErrors = {};
	for (const [field, value] of Object.entries(data)) {
		if (Array.isArray(value) && typeof value[0] === "string") {
			fieldErrors[field] = value[0];
		} else if (typeof value === "string") {
			fieldErrors[field] = value;
		}
	}
	return fieldErrors;
}

function readJSON(key) {
	const value = localStorage.getItem(key);

	if (!value) {
		return null;
	}

	try {
		return JSON.parse(value);
	} catch {
		return null;
	}
}

export function readAuthSession() {
	return {
		accessToken: localStorage.getItem(ACCESS_TOKEN_KEY),
		refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY),
		user: readJSON(USER_KEY),
	};
}

export function setAuthSession({ access, refresh, user }) {
	if (access) {
		localStorage.setItem(ACCESS_TOKEN_KEY, access);
	}

	if (refresh) {
		localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
	}

	if (user) {
		localStorage.setItem(USER_KEY, JSON.stringify(user));
	}
}

export function clearAuthSession() {
	localStorage.removeItem(ACCESS_TOKEN_KEY);
	localStorage.removeItem(REFRESH_TOKEN_KEY);
	localStorage.removeItem(USER_KEY);
}

function getAccessToken() {
	return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken() {
	return localStorage.getItem(REFRESH_TOKEN_KEY);
}

apiClient.interceptors.request.use((config) => {
	const token = getAccessToken();

	if (token) {
		config.headers.Authorization = `Bearer ${token}`;
	}

	return config;
});

let refreshPromise = null;

apiClient.interceptors.response.use(
	(response) => response,
	async (error) => {
		const originalRequest = error.config;

		if (error.response?.status !== 401 || originalRequest?._retry) {
			return Promise.reject(error);
		}

		const refreshToken = getRefreshToken();

		if (!refreshToken) {
			clearAuthSession();
			return Promise.reject(error);
		}

		originalRequest._retry = true;

		try {
			if (!refreshPromise) {
				refreshPromise = authClient
					.post("/token/refresh/", { refresh: refreshToken })
					.then((response) => response.data.access)
					.finally(() => {
						refreshPromise = null;
					});
			}

			const newAccessToken = await refreshPromise;
			localStorage.setItem(ACCESS_TOKEN_KEY, newAccessToken);
			originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;

			return apiClient(originalRequest);
		} catch (refreshError) {
			clearAuthSession();
			return Promise.reject(refreshError);
		}
	}
);

export async function signInRequest(payload) {
	const { data } = await authClient.post("/login/", payload);
	return data;
}

export async function signUpRequest(payload) {
	const { data } = await authClient.post("/signup/", payload);
	return data;
}

export async function googleLoginRequest(credential) {
	const { data } = await authClient.post("/google-login/", { credential });
	return data;
}

export async function verifyEmailOtpRequest({ email, otp }) {
	const { data } = await authClient.post("/verify-email/", { email, otp });
	return data;
}

export async function resendVerificationEmailRequest(email) {
	const { data } = await authClient.post("/verify-email/resend/", { email });
	return data;
}

export async function profileRequest() {
	const { data } = await apiClient.get("/profile/");
	return data;
}

export async function updateProfileRequest({ firstName, avatarFile }) {
	const formData = new FormData();
	if (firstName !== undefined) {
		formData.append("first_name", firstName);
	}
	if (avatarFile) {
		formData.append("avatar", avatarFile);
	}
	const { data } = await apiClient.patch("/profile/", formData);
	return data;
}

export async function changePasswordRequest({ currentPassword, newPassword }) {
	const { data } = await apiClient.post("/profile/change-password/", {
		current_password: currentPassword,
		new_password: newPassword,
	});
	return data;
}

export async function logoutRequest(refreshToken) {
	const { data } = await apiClient.post("/logout/", { refresh: refreshToken });
	return data;
}

export async function requestPasswordResetEmail(email) {
	const { data } = await authClient.post("/password-reset/", { email });
	return data;
}

export async function confirmPasswordReset({ uid, token, newPassword }) {
	const { data } = await authClient.post("/password-reset/confirm/", {
		uid,
		token,
		new_password: newPassword,
	});
	return data;
}

export const tasksApi = {
	list() {
		return apiClient.get("/tasks/");
	},
	get(taskId) {
		return apiClient.get(`/tasks/${taskId}/`);
	},
	create(payload) {
		return apiClient.post("/tasks/", payload);
	},
	createRepeating(payload) {
		return apiClient.post("/tasks/repeat/", payload);
	},
	update(taskId, payload) {
		return apiClient.patch(`/tasks/${taskId}/`, payload);
	},
	remove(taskId) {
		return apiClient.delete(`/tasks/${taskId}/`);
	},
	start(taskId) {
		return apiClient.post(`/tasks/${taskId}/start/`);
	},
	pause(taskId) {
		return apiClient.post(`/tasks/${taskId}/pause/`);
	},
	resume(taskId) {
		return apiClient.post(`/tasks/${taskId}/resume/`);
	},
	stop(taskId) {
		return apiClient.post(`/tasks/${taskId}/stop/`);
	},
	reschedule(taskId, payload) {
		return apiClient.post(`/tasks/${taskId}/reschedule/`, payload);
	},
};

export const categoriesApi = {
	list() {
		return apiClient.get("/categories/");
	},
	create(payload) {
		return apiClient.post("/categories/", payload);
	},
	update(categoryId, payload) {
		return apiClient.patch(`/categories/${categoryId}/`, payload);
	},
	remove(categoryId) {
		return apiClient.delete(`/categories/${categoryId}/`);
	},
};

export const dashboardApi = {
	summary() {
		return apiClient.get("/dashboard/summary/");
	},
	today() {
		return apiClient.get("/dashboard/today/");
	},
	upcoming() {
		return apiClient.get("/dashboard/upcoming/");
	},
	highPriority() {
		return apiClient.get("/dashboard/high-priority/");
	},
	missed() {
		return apiClient.get("/dashboard/missed/");
	},
};

export const adminApi = {
	overview() {
		return apiClient.get("/admin/overview/");
	},
	systemStatus() {
		return apiClient.get("/admin/system-status/");
	},
	users(params) {
		return apiClient.get("/admin/users/", { params });
	},
	userDetail(userId) {
		return apiClient.get(`/admin/users/${userId}/`);
	},
	userTasks(userId) {
		return apiClient.get(`/admin/users/${userId}/tasks/`);
	},
	deactivateUser(userId) {
		return apiClient.post(`/admin/users/${userId}/deactivate/`);
	},
	activateUser(userId) {
		return apiClient.post(`/admin/users/${userId}/activate/`);
	},
	deleteUser(userId) {
		return apiClient.delete(`/admin/users/${userId}/delete/`);
	},
	categoryNames() {
		return apiClient.get("/admin/categories/names/");
	},
	tasks(params) {
		return apiClient.get("/admin/tasks/", { params });
	},
	taskDetail(taskId) {
		return apiClient.get(`/admin/tasks/${taskId}/`);
	},
	updateTask(taskId, payload) {
		return apiClient.patch(`/admin/tasks/${taskId}/`, payload);
	},
	deleteTask(taskId) {
		return apiClient.delete(`/admin/tasks/${taskId}/`);
	},
	triggerReminder(taskId, type) {
		return apiClient.post(`/admin/tasks/${taskId}/trigger-reminder/`, { type });
	},
	async downloadReport(kind) {
		const { data } = await apiClient.get(`/admin/reports/${kind}.csv`, { responseType: "blob" });
		const url = window.URL.createObjectURL(data);
		const link = document.createElement("a");
		link.href = url;
		link.download = `${kind}.csv`;
		document.body.appendChild(link);
		link.click();
		link.remove();
		window.URL.revokeObjectURL(url);
	},
};

export const copilotApi = {
	dashboardSummary() {
		return apiClient.get("/copilot/dashboard-summary/");
	},
	agentStatus() {
		return apiClient.get("/copilot/agent-status/");
	},
	runAgent(agentName) {
		return apiClient.post(`/copilot/agents/${agentName}/run/`);
	},
	runs(params) {
		return apiClient.get("/copilot/runs/", { params });
	},
	runDetail(runId) {
		return apiClient.get(`/copilot/runs/${runId}/`);
	},
	recommendations(params) {
		return apiClient.get("/copilot/recommendations/", { params });
	},
	approveRecommendation(id) {
		return apiClient.post(`/copilot/recommendations/${id}/approve/`);
	},
	rejectRecommendation(id) {
		return apiClient.post(`/copilot/recommendations/${id}/reject/`);
	},
	chatSend(message, sessionId) {
		return apiClient.post("/copilot/chat/send/", { message, session_id: sessionId });
	},
	chatHistory(sessionId) {
		return apiClient.get("/copilot/chat/history/", { params: { session_id: sessionId } });
	},
};

export const evaluationApi = {
	// Runs the full ~20-scenario suite synchronously (real Groq calls) --
	// can take tens of seconds, callers should show a running state.
	trigger() {
		return apiClient.post("/evaluation/run/");
	},
	runs() {
		return apiClient.get("/evaluation/runs/");
	},
	runDetail(runId) {
		return apiClient.get(`/evaluation/runs/${runId}/`);
	},
	summary() {
		return apiClient.get("/evaluation/summary/");
	},
};
