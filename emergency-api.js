"use strict";

(() => {
    const TOKEN_KEY = "resqlink_token";
    const USER_KEY = "resqlink_user";
    const REQUEST_TIMEOUT_MS = 12000;

    class ResqlinkApiError extends Error {
        constructor(message, status = 0, code = "request_failed") {
            super(message);
            this.name = "ResqlinkApiError";
            this.status = status;
            this.code = code;
        }
    }

    function getBaseUrl() {
        const baseUrl = window.RESQLINK_API_URL;
        if (typeof baseUrl !== "string" || !baseUrl.trim()) {
            throw new ResqlinkApiError(
                "The ResQlink API address is not configured.",
                0,
                "configuration"
            );
        }
        return baseUrl.replace(/\/+$/, "");
    }

    function getAccessToken() {
        try {
            return sessionStorage.getItem(TOKEN_KEY);
        } catch (error) {
            throw new ResqlinkApiError(
                "The sign-in session could not be read. Enable browser session storage and try again.",
                0,
                "session_storage"
            );
        }
    }

    function clearSession() {
        try {
            sessionStorage.removeItem(TOKEN_KEY);
            sessionStorage.removeItem(USER_KEY);
        } catch (error) {
            throw new ResqlinkApiError(
                "The expired sign-in session could not be cleared. Sign out and sign in again.",
                0,
                "session_storage"
            );
        }
    }

    async function request(path, options = {}) {
        const token = getAccessToken();
        if (!token) {
            throw new ResqlinkApiError(
                "Sign in to use emergency submissions.",
                401,
                "unauthenticated"
            );
        }

        const controller = new AbortController();
        const timeoutId = window.setTimeout(
            () => controller.abort(),
            REQUEST_TIMEOUT_MS
        );
        let response;
        let data = null;
        try {
            response = await fetch(`${getBaseUrl()}${path}`, {
                ...options,
                headers: {
                    ...(options.headers || {}),
                    Authorization: `Bearer ${token}`
                },
                signal: controller.signal
            });
            try {
                data = await response.json();
            } catch (error) {
                data = null;
            }
        } catch (error) {
            if (error && error.name === "AbortError") {
                throw new ResqlinkApiError(
                    "The request timed out. The alert may still have been saved; retry the same request.",
                    0,
                    "timeout"
                );
            }
            throw new ResqlinkApiError(
                "Could not reach the ResQlink API. Check your connection and retry.",
                0,
                "network"
            );
        } finally {
            window.clearTimeout(timeoutId);
        }

        if (response.status === 401) {
            try {
                clearSession();
            } catch (error) {
                throw error;
            }
            throw new ResqlinkApiError(
                "Your session expired. Sign in, then retry the same alert.",
                401,
                "expired"
            );
        }
        if (!response.ok) {
            const detail = data && typeof data.detail === "string"
                ? data.detail
                : `The ResQlink API returned status ${response.status}.`;
            throw new ResqlinkApiError(detail, response.status, "api_error");
        }
        return data;
    }

    async function getCurrentUser() {
        const data = await request("/me", { method: "GET" });
        if (
            !data
            || typeof data.id !== "string"
            || typeof data.name !== "string"
            || typeof data.role !== "string"
        ) {
            throw new ResqlinkApiError(
                "The API did not return a valid signed-in profile.",
                502,
                "invalid_profile"
            );
        }
        return data;
    }

    async function submitEmergency(payload, idempotencyKey) {
        const data = await request("/emergency", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": idempotencyKey
            },
            body: JSON.stringify(payload)
        });
        if (
            !data
            || !Number.isInteger(data.alert_id)
            || data.alert_id < 1
            || !["ACTIVE", "RESOLVED"].includes(data.status)
            || !["submitted", "already_submitted"].includes(data.submission_status)
        ) {
            throw new ResqlinkApiError(
                "The API response did not confirm an alert ID and status. Retry the same request.",
                502,
                "invalid_submission_response"
            );
        }
        return data;
    }

    window.ResqlinkApi = Object.freeze({
        getCurrentUser,
        submitEmergency,
        clearSession
    });
})();
