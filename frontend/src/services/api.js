import axios from "axios";

export const API_ROOT = import.meta.env.VITE_API_ROOT || "/api";

// The access token lives ONLY here -- a module-level variable, never
// localStorage/sessionStorage. It disappears on tab close and on every
// hard reload, by design: an XSS payload running on this page could still
// read it out of memory while the tab is open (nothing in a browser can
// fully prevent that), but it can no longer be exfiltrated as a durable,
// replayable credential the way a localStorage value can. The refresh
// token never reaches JS at all -- see the withCredentials/cookie setup
// below and backend/users/token_cookies.py. See SECURITY.md's "Token
// storage" section for the full threat model.
let accessToken = null;

export function getAccessToken() {
	return accessToken;
}

export function setAccessToken(token) {
	accessToken = token || null;
}

// `withCredentials: true` is required on every client so the browser
// attaches (and stores) the HttpOnly refresh-token cookie the backend
// sets on login/signup/etc. and reads back on /token/refresh/ and
// /logout/ -- see backend's CORS_ALLOW_CREDENTIALS setting, which only
// permits this for the explicit origin allowlist, never a wildcard.
const authClient = axios.create({
	baseURL: API_ROOT,
	withCredentials: true,
});

const apiClient = axios.create({
	baseURL: API_ROOT,
	withCredentials: true,
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

// Calls /token/refresh/ with no arguments -- the refresh token travels
// entirely in the HttpOnly cookie the browser attaches automatically
// (withCredentials above), never touched or read by this code. Used both
// to silently re-establish a session on app load (the access token in
// memory is gone after any hard reload) and by the 401 retry logic below.
// Returns the new access token, or null if there's no valid session to
// resume (no cookie, or an expired/blacklisted one).
async function refreshAccessToken() {
	try {
		const { data } = await authClient.post("/token/refresh/");
		setAccessToken(data.access);
		return data.access;
	} catch {
		setAccessToken(null);
		return null;
	}
}

// Called once on app startup (see AuthContext) to resume a session from
// the refresh cookie, if any -- replaces the old synchronous
// "read tokens out of localStorage" bootstrap with a network round trip,
// since there's nothing left in persistent client storage to read.
export async function bootstrapSession() {
	return refreshAccessToken();
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

		originalRequest._retry = true;

		if (!refreshPromise) {
			refreshPromise = refreshAccessToken().finally(() => {
				refreshPromise = null;
			});
		}

		const newAccessToken = await refreshPromise;

		if (!newAccessToken) {
			return Promise.reject(error);
		}

		originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
		return apiClient(originalRequest);
	}
);

// The four endpoints below are the only ones that ever hand back a fresh
// access token (signup itself doesn't -- it requires OTP verification
// first). Each stores it in memory here, right where the response is
// received, rather than leaving every caller responsible for remembering
// to -- the refresh token needs no equivalent handling since it arrives
// as a Set-Cookie header the browser stores on its own.
export async function signInRequest(payload) {
	const { data } = await authClient.post("/login/", payload);
	setAccessToken(data.access);
	return data;
}

export async function signUpRequest(payload) {
	const { data } = await authClient.post("/signup/", payload);
	return data;
}

export async function googleLoginRequest(credential) {
	const { data } = await authClient.post("/google-login/", { credential });
	setAccessToken(data.access);
	return data;
}

export async function verifyEmailOtpRequest({ email, otp }) {
	const { data } = await authClient.post("/verify-email/", { email, otp });
	setAccessToken(data.access);
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

export async function updateProfileRequest({ firstName = undefined, avatarFile = undefined }) {
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
	// The backend revokes every outstanding refresh token (including this
	// device's) and clears the refresh cookie the moment a password
	// change succeeds -- see backend/users/views.py::change_password --
	// so this device's session is over too, not just other devices'. The
	// caller is expected to treat this the same as a forced logout.
	setAccessToken(null);
	return data;
}

export async function logoutRequest() {
	try {
		const { data } = await apiClient.post("/logout/");
		return data;
	} finally {
		// Regardless of whether the network call itself succeeded -- this
		// client's copy of the session ends either way.
		setAccessToken(null);
	}
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
	setAccessToken(data.access);
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

// Separate from copilotApi (which is admin-only end to end) -- this is the
// per-user AI Copilot: any authenticated user can call it, and it only
// ever sees/acts on that one user's own tasks/categories. Fully stateless
// on the backend -- `history` is held client-side and resent every call,
// never persisted server-side (see usercopilot/services/chat_service.py).
export const userCopilotApi = {
	status() {
		return apiClient.get("/usercopilot/status/");
	},
	chatSend(message, history) {
		return apiClient.post("/usercopilot/chat/send/", { message, history });
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
