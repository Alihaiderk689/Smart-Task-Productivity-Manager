import {
	categoriesApi,
	fetchPage,
	logoutRequest,
	profileRequest,
	signInRequest,
	signUpRequest,
	tasksApi,
} from "../services/api";

function unwrap(response) {
	return response?.data ?? response;
}

// The backend paginates /api/tasks/ and /api/categories/ ({count, next,
// previous, results} -- see core/pagination.py's DefaultListPagination), one
// bounded page at a time. Every current caller of Task.list()/Category.list()
// (Home, Tasks, TaskDetail, Categories, Calendar, components/layout.jsx)
// expects "every one of this user's tasks/categories" -- none of them have
// load-more UI -- so this follows `next` until exhausted and returns the
// full, concatenated list. Each individual request server-side still stays
// bounded (page_size/max_page_size), this just makes as many of them as
// needed instead of silently stopping at page 1.
async function fetchAllPages(firstPageRequest) {
	let data = unwrap(await firstPageRequest());
	let results = data.results;
	let next = data.next;

	while (next) {
		data = unwrap(await fetchPage(next));
		results = results.concat(data.results);
		next = data.next;
	}

	return results;
}

export const base44 = {
	auth: {
		async loginViaEmailPassword(email, password) {
			return signInRequest({ email, password });
		},
		async register(payload) {
			return signUpRequest(payload);
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
		async logout(redirectTo = "/login") {
			try {
				await logoutRequest();
			} finally {
				if (redirectTo) {
					window.location.href = redirectTo;
				}
			}
		},
	},
	entities: {
		Task: {
			async list() {
				return fetchAllPages(() => tasksApi.list());
			},
			async get(taskId) {
				return unwrap(await tasksApi.get(taskId));
			},
			async create(payload) {
				return unwrap(await tasksApi.create(payload));
			},
			async createRepeating(payload) {
				return unwrap(await tasksApi.createRepeating(payload));
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
			async reschedule(taskId, payload) {
				return unwrap(await tasksApi.reschedule(taskId, payload));
			},
		},
		Category: {
			async list() {
				return fetchAllPages(() => categoriesApi.list());
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