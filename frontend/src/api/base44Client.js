import {
	clearAuthSession,
	categoriesApi,
	logoutRequest,
	profileRequest,
	readAuthSession,
	setAuthSession,
	signInRequest,
	signUpRequest,
	tasksApi,
} from "../services/api";

function unwrap(response) {
	return response?.data ?? response;
}

function persistAuthSession(response) {
	setAuthSession({
		access: response.access,
		refresh: response.refresh,
		user: response.user,
	});

	return response;
}

export const base44 = {
	auth: {
		async loginViaEmailPassword(email, password) {
			return persistAuthSession(await signInRequest({ email, password }));
		},
		async register(payload) {
			return persistAuthSession(await signUpRequest(payload));
		},
		async verifyOtp() {
			throw new Error("Email verification is not handled by this backend.");
		},
		async resendOtp() {
			throw new Error("Email verification is not handled by this backend.");
		},
		loginWithProvider() {
			window.location.href = "/login";
		},
		async resetPasswordRequest() {
			throw new Error("Password reset is not available in this backend.");
		},
		async resetPassword() {
			throw new Error("Password reset is not available in this backend.");
		},
		async me() {
			return profileRequest();
		},
		setToken(token) {
			const session = readAuthSession();
			setAuthSession({
				access: token,
				refresh: session.refreshToken,
				user: session.user,
			});
		},
		async logout(redirectTo = "/login") {
			const session = readAuthSession();

			try {
				if (session.refreshToken) {
					await logoutRequest(session.refreshToken);
				}
			} finally {
				clearAuthSession();
				if (redirectTo) {
					window.location.href = redirectTo;
				}
			}
		},
	},
	entities: {
		Task: {
			async list() {
				return unwrap(await tasksApi.list());
			},
			async get(taskId) {
				return unwrap(await tasksApi.get(taskId));
			},
			async create(payload) {
				return unwrap(await tasksApi.create(payload));
			},
			async update(taskId, payload) {
				return unwrap(await tasksApi.update(taskId, payload));
			},
			async delete(taskId) {
				return unwrap(await tasksApi.remove(taskId));
			},
			async start(taskId) {
				return unwrap(await tasksApi.start(taskId));
			},
			async pause(taskId) {
				return unwrap(await tasksApi.pause(taskId));
			},
			async resume(taskId) {
				return unwrap(await tasksApi.resume(taskId));
			},
			async stop(taskId) {
				return unwrap(await tasksApi.stop(taskId));
			},
			async complete(taskId) {
				return unwrap(await tasksApi.complete(taskId));
			},
			async reschedule(taskId, payload) {
				return unwrap(await tasksApi.reschedule(taskId, payload));
			},
		},
		Category: {
			async list() {
				return unwrap(await categoriesApi.list());
			},
			async create(payload) {
				return unwrap(await categoriesApi.create(payload));
			},
			async update(categoryId, payload) {
				return unwrap(await categoriesApi.update(categoryId, payload));
			},
			async delete(categoryId) {
				return unwrap(await categoriesApi.remove(categoryId));
			},
		},
	},
};