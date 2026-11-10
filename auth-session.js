"use strict";

(() => {
    const TOKEN_KEY = "resqlink_token";
    const LEGACY_USER_KEY = "resqlink_user";
    const REQUEST_TIMEOUT_MS = 12000;

    class AuthError extends Error {
        constructor(message, status = 0, code = "request_failed") {
            super(message);
            this.name = "AuthError";
            this.status = status;
            this.code = code;
        }
    }

    function apiBaseUrl() {
        const value = window.RESQLINK_API_URL;
        if (typeof value !== "string" || !value.trim()) {
            throw new AuthError("The ResQlink API address is not configured.", 0, "configuration");
        }
        return value.replace(/\/+$/, "");
    }

    function getAccessToken() {
        try {
            sessionStorage.removeItem(LEGACY_USER_KEY);
            return sessionStorage.getItem(TOKEN_KEY);
        } catch (error) {
            throw new AuthError(
                "Browser session storage is unavailable. Enable it and try again.",
                0,
                "session_storage"
            );
        }
    }

    function storeAccessToken(token) {
        if (typeof token !== "string" || !token.trim()) {
            throw new AuthError("The API did not return a valid sign-in session.", 502, "invalid_session");
        }
        try {
            sessionStorage.setItem(TOKEN_KEY, token);
            sessionStorage.removeItem(LEGACY_USER_KEY);
        } catch (error) {
            throw new AuthError(
                "The sign-in session could not be saved in this tab.",
                0,
                "session_storage"
            );
        }
    }

    function clearSession() {
        try {
            sessionStorage.removeItem(TOKEN_KEY);
            sessionStorage.removeItem(LEGACY_USER_KEY);
        } catch (error) {
            throw new AuthError(
                "The sign-in session could not be cleared. Close this tab and sign in again.",
                0,
                "session_storage"
            );
        }
    }

    async function logout() {
        const token = getAccessToken();
        try {
            if (token) {
                await request("/logout", {
                    method: "POST",
                    accessToken: token
                });
            }
        } finally {
            clearSession();
        }
    }

    async function request(path, options = {}) {
        const {
            accessToken,
            skipSessionToken = false,
            ...fetchOptions
        } = options;
        const token = accessToken || (skipSessionToken ? null : getAccessToken());
        const headers = new Headers(fetchOptions.headers || {});
        if (token) headers.set("Authorization", `Bearer ${token}`);
        const url = `${apiBaseUrl()}${path}`;

        const controller = new AbortController();
        const timeoutId = window.setTimeout(
            () => controller.abort(),
            REQUEST_TIMEOUT_MS
        );
        let response;
        let data = null;
        try {
            response = await fetch(url, {
                ...fetchOptions,
                headers,
                signal: controller.signal
            });
            try {
                data = await response.json();
            } catch (error) {
                data = null;
            }
        } catch (error) {
            if (error && error.name === "AbortError") {
                throw new AuthError(
                    "The request timed out. Check your connection and try again.",
                    0,
                    "timeout"
                );
            }
            throw new AuthError(
                "Could not reach the ResQlink API. Check your connection and try again.",
                0,
                "network"
            );
        } finally {
            window.clearTimeout(timeoutId);
        }

        if (response.status === 401) {
            if (accessToken) {
                clearSession();
                throw new AuthError(
                    "Your session is invalid or expired. Sign in again.",
                    401,
                    "expired"
                );
            }
            if (token) clearSession();
            if (skipSessionToken || !token) {
                const detail = data && typeof data.detail === "string"
                    ? data.detail
                    : "The request was not authorized.";
                throw new AuthError(detail, 401, "api_error");
            }
            throw new AuthError(
                "Your session is invalid or expired. Sign in again.",
                401,
                "expired"
            );
        }
        if (!response.ok) {
            const detail = data && typeof data.detail === "string"
                ? data.detail
                : `The ResQlink API returned status ${response.status}.`;
            throw new AuthError(detail, response.status, "api_error");
        }
        return data;
    }

    async function getCurrentUser() {
        const token = getAccessToken();
        if (!token) {
            throw new AuthError("Sign in to continue.", 401, "unauthenticated");
        }
        const data = await request("/me", { method: "GET", accessToken: token });
        if (
            !data
            || typeof data.id !== "string"
            || typeof data.name !== "string"
            || typeof data.role !== "string"
        ) {
            throw new AuthError(
                "The API did not return a valid signed-in profile.",
                502,
                "invalid_profile"
            );
        }
        return data;
    }

    window.ResqlinkAuth = Object.freeze({
        AuthError,
        clearSession,
        getAccessToken,
        getCurrentUser,
        logout,
        request,
        storeAccessToken
    });
})();
