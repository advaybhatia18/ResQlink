"use strict";

(() => {
    const auth = window.ResqlinkAuth;

    function showMessage(element, text, state = "error") {
        element.textContent = text;
        element.dataset.state = state;
    }

    function setBusy(button, busy, label) {
        button.disabled = busy;
        button.textContent = busy ? label : button.dataset.defaultLabel;
    }

    function postLoginDestination() {
        const target = new URLSearchParams(window.location.search).get("next");
        return target === "dashboard.html" ? "dashboard.html" : "index.html";
    }

    function configurePasswordToggles() {
        document.querySelectorAll("[data-password-toggle]").forEach(toggle => {
            const input = document.getElementById(toggle.dataset.passwordToggle);
            if (!input) return;
            toggle.addEventListener("click", () => {
                const visible = input.type === "password";
                input.type = visible ? "text" : "password";
                toggle.textContent = visible ? "Hide" : "Show";
                toggle.setAttribute("aria-pressed", String(visible));
                const label = toggle.getAttribute("aria-label") || "";
                toggle.setAttribute(
                    "aria-label",
                    visible ? label.replace(/^Show/, "Hide") : label.replace(/^Hide/, "Show")
                );
            });
        });
    }

    async function redirectIfSignedIn(message) {
        try {
            if (!auth.getAccessToken()) return;
        } catch (error) {
            showMessage(message, error.message);
            return;
        }
        try {
            await auth.getCurrentUser();
            window.location.replace(postLoginDestination());
        } catch (error) {
            if (error.code !== "expired" && error.code !== "unauthenticated") {
                showMessage(message, `${error.message} You can still try to sign in.`, "error");
            } else {
                showMessage(message, "Your previous session expired. Sign in again.", "notice");
            }
        }
    }

    function setupLogin() {
        const form = document.getElementById("loginForm");
        if (!form) return;
        const message = document.getElementById("loginMessage");
        const button = document.getElementById("loginButton");
        button.dataset.defaultLabel = button.textContent.trim();
        const recoveryForm = document.getElementById("recoveryForm");
        const recoveryLink = document.getElementById("forgotLink");
        const recoveryEmail = document.getElementById("recoveryEmail");
        const recoveryButton = document.getElementById("recoveryButton");
        recoveryButton.dataset.defaultLabel = recoveryButton.textContent.trim();
        if (new URLSearchParams(window.location.search).get("logout") === "local") {
            showMessage(
                message,
                "Signed out on this device. The API could not confirm server-side revocation; any unrevoked access expires automatically.",
                "notice"
            );
        }
        if (new URLSearchParams(window.location.search).get("expired") === "1") {
            showMessage(message, "Your session expired. Sign in again to continue.", "notice");
        }

        form.addEventListener("submit", async event => {
            event.preventDefault();
            if (!form.reportValidity()) return;
            const email = document.getElementById("email").value.trim();
            const password = document.getElementById("password").value;
            setBusy(button, true, "Verifying sign-in…");
            showMessage(message, "");
            try {
                const result = await auth.request("/login", {
                    method: "POST",
                    skipSessionToken: true,
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email, password })
                });
                auth.storeAccessToken(result && result.access_token);
                await auth.getCurrentUser();
                showMessage(message, "Signed in. Opening your account…", "success");
                window.location.replace(postLoginDestination());
            } catch (error) {
                showMessage(message, error.message);
            } finally {
                setBusy(button, false, "Verifying sign-in…");
            }
        });

        recoveryLink.addEventListener("click", event => {
            event.preventDefault();
            recoveryForm.hidden = false;
            recoveryEmail.value = document.getElementById("email").value.trim();
            recoveryEmail.focus();
            recoveryForm.scrollIntoView({ block: "nearest", behavior: "smooth" });
        });

        recoveryForm.addEventListener("submit", async event => {
            event.preventDefault();
            if (!recoveryForm.reportValidity()) return;
            setBusy(recoveryButton, true, "Sending instructions…");
            showMessage(document.getElementById("recoveryMessage"), "");
            try {
                const result = await auth.request("/password-recovery", {
                    method: "POST",
                    skipSessionToken: true,
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: recoveryEmail.value.trim() })
                });
                showMessage(
                    document.getElementById("recoveryMessage"),
                    result.message || "If an account exists for that email, recovery instructions will be sent.",
                    "success"
                );
            } catch (error) {
                showMessage(document.getElementById("recoveryMessage"), error.message);
            } finally {
                setBusy(recoveryButton, false, "Sending instructions…");
            }
        });
        redirectIfSignedIn(message);
    }

    function setupRegistration() {
        const form = document.getElementById("registerForm");
        if (!form) return;
        const message = document.getElementById("registerMessage");
        const button = document.getElementById("registerButton");
        button.dataset.defaultLabel = button.textContent.trim();

        form.addEventListener("submit", async event => {
            event.preventDefault();
            const name = document.getElementById("name");
            const email = document.getElementById("email");
            const password = document.getElementById("password");
            const confirmation = document.getElementById("confirmPassword");
            name.value = name.value.trim();
            email.value = email.value.trim();
            if (!form.reportValidity()) return;
            if (password.value !== confirmation.value) {
                confirmation.setCustomValidity("Passwords do not match.");
                confirmation.reportValidity();
                confirmation.setCustomValidity("");
                return;
            }

            setBusy(button, true, "Creating account…");
            showMessage(message, "");
            try {
                await auth.request("/register", {
                    method: "POST",
                    skipSessionToken: true,
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        name: name.value,
                        email: email.value,
                        password: password.value
                    })
                });
                form.reset();
                showMessage(
                    message,
                    "Account created. If email confirmation is enabled, verify your address before signing in.",
                    "success"
                );
                window.setTimeout(() => window.location.assign("login.html"), 1800);
            } catch (error) {
                showMessage(message, error.message);
            } finally {
                setBusy(button, false, "Creating account…");
            }
        });
        redirectIfSignedIn(message);
    }

    function setupPasswordReset() {
        const form = document.getElementById("passwordResetForm");
        if (!form) return;
        const message = document.getElementById("resetMessage");
        const button = document.getElementById("resetButton");
        const hashParams = new URLSearchParams(window.location.hash.slice(1));
        const queryParams = new URLSearchParams(window.location.search);
        let recoveryToken = hashParams.get("access_token") || queryParams.get("access_token");
        const type = hashParams.get("type") || queryParams.get("type");
        button.dataset.defaultLabel = button.textContent.trim();
        if (recoveryToken && type === "recovery") {
            window.history.replaceState(null, document.title, window.location.pathname);
            form.hidden = false;
            showMessage(message, "Choose a new password for your account.", "notice");
        } else {
            form.hidden = true;
            showMessage(
                message,
                "This recovery link is missing or invalid. Request a new link from the sign-in page.",
                "error"
            );
        }

        form.addEventListener("submit", async event => {
            event.preventDefault();
            if (!recoveryToken || !form.reportValidity()) return;
            const password = document.getElementById("newPassword");
            const confirmation = document.getElementById("confirmNewPassword");
            if (password.value !== confirmation.value) {
                confirmation.setCustomValidity("Passwords do not match.");
                confirmation.reportValidity();
                confirmation.setCustomValidity("");
                return;
            }
            setBusy(button, true, "Updating password…");
            try {
                await auth.request("/password-update", {
                    method: "POST",
                    accessToken: recoveryToken,
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ password: password.value })
                });
                let successMessage =
                    "Password updated. You can now sign in with your new password.";
                try {
                    auth.clearSession();
                } catch (error) {
                    successMessage += " Close this tab to clear its existing sign-in session.";
                }
                recoveryToken = null;
                showMessage(
                    message,
                    successMessage,
                    "success"
                );
                form.reset();
                button.disabled = true;
                window.setTimeout(() => window.location.assign("login.html"), 1500);
            } catch (error) {
                if (error.code === "expired" || error.status === 401) {
                    recoveryToken = null;
                    showMessage(
                        message,
                        "This recovery link has expired. Request a new password recovery email.",
                        "error"
                    );
                    form.hidden = true;
                } else {
                    showMessage(message, error.message);
                }
            } finally {
                if (!button.disabled) setBusy(button, false, "Updating password…");
            }
        });
    }

    configurePasswordToggles();
    setupLogin();
    setupRegistration();
    setupPasswordReset();
})();
