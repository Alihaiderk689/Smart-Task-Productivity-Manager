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

	if (!data) {
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

export async function profileRequest() {
	const { data } = await apiClient.get("/profile/");
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
	complete(taskId) {
		return apiClient.post(`/tasks/${taskId}/complete/`);
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
