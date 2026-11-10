"use strict";

(() => {
    const PENDING_ATTEMPT_KEY = "resqlink_pending_emergency";
    const API_TIMEOUT_MS = 12000;
    const GPS_TIMEOUT_MS = 15000;
    const MAX_ACCEPTABLE_ACCURACY_M = 100;
    const elements = {
        button: document.getElementById("sosButton"),
        status: document.getElementById("status"),
        latitude: document.getElementById("latitude"),
        longitude: document.getElementById("longitude"),
        accuracy: document.getElementById("locationAccuracy"),
        locationActions: document.getElementById("locationActions"),
        locationMessage: document.getElementById("locationMessage"),
        retryLocation: document.getElementById("retryLocationButton"),
        useApproximate: document.getElementById("useApproximateLocationButton"),
        withoutLocation: document.getElementById("submitWithoutLocationButton"),
        signInLink: document.getElementById("signInLink"),
        severity: document.getElementById("severity")
    };
    let isSubmitting = false;
    let pendingAttemptCorrupt = false;
    let approximateLocation = null;
    let pendingAttempt = readPendingAttempt();

    function setStatus(message) {
        elements.status.textContent = message;
    }

    function validCoordinates(coords) {
        return coords
            && typeof coords.latitude === "number"
            && Number.isFinite(coords.latitude)
            && coords.latitude >= -90
            && coords.latitude <= 90
            && typeof coords.longitude === "number"
            && Number.isFinite(coords.longitude)
            && coords.longitude >= -180
            && coords.longitude <= 180
            && typeof coords.accuracy === "number"
            && Number.isFinite(coords.accuracy)
            && coords.accuracy >= 0;
    }

    function readPendingAttempt() {
        try {
            const saved = sessionStorage.getItem(PENDING_ATTEMPT_KEY);
            if (!saved) return null;
            const attempt = JSON.parse(saved);
            const payload = attempt && attempt.payload;
            const hasCoordinates = payload
                && payload.latitude !== null
                && payload.longitude !== null;
            const coordinatesValid = hasCoordinates
                ? typeof payload.latitude === "number"
                    && Number.isFinite(payload.latitude)
                    && payload.latitude >= -90
                    && payload.latitude <= 90
                    && typeof payload.longitude === "number"
                    && Number.isFinite(payload.longitude)
                    && payload.longitude >= -180
                    && payload.longitude <= 180
                : payload
                    && payload.latitude === null
                    && payload.longitude === null;
            const accuracyValid = payload
                && (
                    payload.location_accuracy_m === null
                    || (
                        hasCoordinates
                        && typeof payload.location_accuracy_m === "number"
                        && Number.isFinite(payload.location_accuracy_m)
                        && payload.location_accuracy_m >= 0
                    )
                );
            if (
                attempt
                && typeof attempt.key === "string"
                && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(attempt.key)
                && payload
                && Number.isInteger(payload.severity)
                && payload.severity >= 1
                && payload.severity <= 5
                && coordinatesValid
                && accuracyValid
                && typeof payload.location_accuracy_confirmed === "boolean"
                && (hasCoordinates || !payload.location_accuracy_confirmed)
                && (
                    payload.location_accuracy_m === null
                    || payload.location_accuracy_m <= MAX_ACCEPTABLE_ACCURACY_M
                    || payload.location_accuracy_confirmed
                )
            ) {
                return attempt;
            }
            setStatus(
                "A saved alert retry could not be verified. Do not assume it was submitted; contact your administrator before starting another test alert."
            );
            pendingAttemptCorrupt = true;
        } catch (error) {
            setStatus(
                "The saved alert retry could not be read. Do not assume it was submitted; contact your administrator before starting another test alert."
            );
            pendingAttemptCorrupt = true;
        }
        return null;
    }

    function makeIdempotencyKey() {
        if (!window.crypto || !window.crypto.getRandomValues) {
            throw new Error("Secure request IDs are unavailable in this browser.");
        }
        if (window.crypto.randomUUID) return window.crypto.randomUUID();

        const bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0"));
        return [
            hex.slice(0, 4).join(""),
            hex.slice(4, 6).join(""),
            hex.slice(6, 8).join(""),
            hex.slice(8, 10).join(""),
            hex.slice(10).join("")
        ].join("-");
    }

    function locationErrorMessage(error) {
        if (!navigator.geolocation) {
            return "This browser does not provide GPS location.";
        }
        if (error && error.code === 1) {
            return "Location permission was denied.";
        }
        if (error && error.code === 2) {
            return "The device could not determine your location.";
        }
        if (error && error.code === 3) {
            return "GPS timed out before a location was available.";
        }
        return "Your location is unavailable right now.";
    }

    function getCurrentLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject({ code: 2 });
                return;
            }
            navigator.geolocation.getCurrentPosition(
                position => resolve(position.coords),
                reject,
                {
                    enableHighAccuracy: true,
                    timeout: GPS_TIMEOUT_MS,
                    maximumAge: 0
                }
            );
        });
    }

    function showLocationFallback(message, allowApproximate = false) {
        elements.locationMessage.textContent = message;
        elements.locationActions.hidden = false;
        elements.useApproximate.hidden = !allowApproximate;
        elements.withoutLocation.hidden = false;
    }

    function hideLocationFallback() {
        elements.locationActions.hidden = true;
        elements.useApproximate.hidden = true;
        elements.withoutLocation.hidden = true;
    }

    async function acquireLocation() {
        if (isSubmitting) return;
        elements.button.disabled = true;
        elements.retryLocation.disabled = true;
        elements.withoutLocation.disabled = true;
        elements.useApproximate.disabled = true;
        elements.latitude.textContent = "Latitude: Locating...";
        elements.longitude.textContent = "Longitude: Locating...";
        elements.accuracy.textContent = "Accuracy: Measuring...";
        setStatus("Requesting a fresh GPS location...");

        try {
            const coords = await getCurrentLocation();
            if (!validCoordinates(coords)) {
                throw new Error("The browser returned invalid or inaccurate coordinates.");
            }

            approximateLocation = {
                latitude: coords.latitude,
                longitude: coords.longitude,
                location_accuracy_m: coords.accuracy
            };
            elements.latitude.textContent = `Latitude: ${coords.latitude}`;
            elements.longitude.textContent = `Longitude: ${coords.longitude}`;
            elements.accuracy.textContent =
                `Estimated accuracy: within ${Math.round(coords.accuracy)} m`;

            if (coords.accuracy > MAX_ACCEPTABLE_ACCURACY_M) {
                const warning =
                    `GPS accuracy is approximately ${Math.round(coords.accuracy)} m, which may be imprecise. Retry for a better fix or explicitly choose to submit this approximate location.`;
                showLocationFallback(warning, true);
                setStatus("Location obtained, but needs your confirmation.");
                return;
            }

            hideLocationFallback();
            await createAndSubmitAttempt(approximateLocation);
        } catch (error) {
            approximateLocation = null;
            elements.latitude.textContent = "Latitude: Not available";
            elements.longitude.textContent = "Longitude: Not available";
            elements.accuracy.textContent = "Accuracy: Not available";
            const message = error && error.code
                ? locationErrorMessage(error)
                : (error && error.message) || locationErrorMessage(error);
            showLocationFallback(
                `${message} Retry GPS, or deliberately submit this alert without coordinates. No location will be invented.`
            );
            setStatus("No alert was submitted because a location is not yet available.");
        } finally {
            elements.button.disabled = false;
            elements.retryLocation.disabled = false;
            elements.withoutLocation.disabled = false;
            elements.useApproximate.disabled = false;
        }
    }

    async function createAndSubmitAttempt(location) {
        const severity = Number(elements.severity.value);
        if (!Number.isInteger(severity) || severity < 1 || severity > 5) {
            setStatus("Choose a severity from 1 to 5 before submitting.");
            return;
        }

        let attempt;
        try {
            attempt = {
                key: makeIdempotencyKey(),
                payload: {
                    severity,
                    latitude: location ? location.latitude : null,
                    longitude: location ? location.longitude : null,
                    location_accuracy_m: location
                        ? location.location_accuracy_m
                        : null,
                    location_accuracy_confirmed: Boolean(
                        location
                        && location.location_accuracy_m > MAX_ACCEPTABLE_ACCURACY_M
                    )
                }
            };
            sessionStorage.setItem(PENDING_ATTEMPT_KEY, JSON.stringify(attempt));
        } catch (error) {
            setStatus(
                "This browser could not save a safe retry key. The alert was not sent; enable session storage and try again."
            );
            return;
        }
        pendingAttempt = attempt;
        elements.severity.disabled = true;
        await submitAttempt(attempt);
    }

    async function submitAttempt(attempt) {
        if (isSubmitting) return;
        let accessToken;
        try {
            accessToken = sessionStorage.getItem("resqlink_token");
        } catch (error) {
            setStatus("The sign-in session could not be read. No request was sent.");
            return;
        }
        if (!accessToken) {
            elements.signInLink.hidden = false;
            elements.button.textContent = "Sign in to retry";
            setStatus(
                "Your session is missing or expired. This alert is preserved for a safe retry after you sign in."
            );
            return;
        }

        isSubmitting = true;
        elements.button.disabled = true;
        elements.button.textContent = "Submitting...";
        setStatus("Submitting to the ResQlink demo server...");
        const controller = new AbortController();
        const timeout = window.setTimeout(
            () => controller.abort(),
            API_TIMEOUT_MS
        );

        try {
            const response = await fetch(
                `${window.RESQLINK_API_URL}/emergency`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${accessToken}`,
                        "Idempotency-Key": attempt.key
                    },
                    body: JSON.stringify(attempt.payload),
                    signal: controller.signal
                }
            );
            let data = null;
            try {
                data = await response.json();
            } catch (error) {
                data = null;
            }

            if (response.status === 401) {
                elements.signInLink.hidden = false;
                elements.button.textContent = "Sign in to retry";
                let sessionCleared = true;
                try {
                    sessionStorage.removeItem("resqlink_token");
                    sessionStorage.removeItem("resqlink_user");
                } catch (error) {
                    sessionCleared = false;
                }
                const sessionNote = sessionCleared
                    ? ""
                    : " The expired browser token could not be cleared automatically.";
                setStatus(
                    `Your session expired before the server could confirm this alert. Sign in, then retry the same request safely.${sessionNote}`
                );
                return;
            }
            if (!response.ok) {
                const detail = data && typeof data.detail === "string"
                    ? ` ${data.detail}`
                    : "";
                throw new Error(`The server returned ${response.status}.${detail}`);
            }
            if (
                !data
                || !Number.isInteger(data.alert_id)
                || data.alert_id < 1
                || !["ACTIVE", "RESOLVED"].includes(data.status)
                || !["submitted", "already_submitted"].includes(data.submission_status)
            ) {
                throw new Error("The server response did not confirm an alert ID and status.");
            }

            let retryKeyCleared = true;
            try {
                sessionStorage.removeItem(PENDING_ATTEMPT_KEY);
            } catch (error) {
                retryKeyCleared = false;
            }
            if (retryKeyCleared) {
                pendingAttempt = null;
                elements.severity.disabled = false;
            }
            elements.signInLink.hidden = true;
            hideLocationFallback();
            const recorded = data.submission_status === "already_submitted"
                ? "This alert was already recorded"
                : "Alert recorded";
            const locationNote = attempt.payload.latitude === null
                ? " without location"
                : "";
            const cleanupNote = retryKeyCleared
                ? ""
                : " The alert is confirmed, but the browser could not clear its retry key; close this tab before creating another alert.";
            setStatus(
                `${recorded}${locationNote} as #${data.alert_id} (${data.status}) in the ResQlink demo. Emergency services were not contacted.${cleanupNote}`
            );
            elements.button.textContent = retryKeyCleared
                ? "SOS"
                : "Retry same alert";
        } catch (error) {
            const detail = error && error.name === "AbortError"
                ? "The request timed out; the server may still have saved it."
                : (error && error.message) || "The server could not confirm the submission.";
            setStatus(
                `${detail} No confirmation was received. Press the button to retry the same alert safely.`
            );
            elements.button.textContent = "Retry same alert";
        } finally {
            window.clearTimeout(timeout);
            isSubmitting = false;
            elements.button.disabled = false;
        }
    }

    async function sendAlert() {
        if (pendingAttemptCorrupt) return;
        if (pendingAttempt) {
            await submitAttempt(pendingAttempt);
            return;
        }
        let accessToken;
        try {
            accessToken = sessionStorage.getItem("resqlink_token");
        } catch (error) {
            setStatus("The sign-in session could not be read. No request was sent.");
            return;
        }
        if (!accessToken) {
            elements.signInLink.hidden = false;
            setStatus("Sign in before submitting an alert.");
            return;
        }
        await acquireLocation();
    }

    elements.button.addEventListener("click", sendAlert);
    elements.retryLocation.addEventListener("click", acquireLocation);
    elements.withoutLocation.addEventListener("click", () => {
        approximateLocation = null;
        elements.latitude.textContent = "Latitude: Not provided";
        elements.longitude.textContent = "Longitude: Not provided";
        elements.accuracy.textContent = "Accuracy: Not available";
        hideLocationFallback();
        createAndSubmitAttempt(null);
    });
    elements.useApproximate.addEventListener("click", () => {
        if (approximateLocation) {
            hideLocationFallback();
            createAndSubmitAttempt(approximateLocation);
        }
    });

    if (pendingAttempt) {
        const payload = pendingAttempt.payload;
        elements.severity.value = String(payload.severity);
        elements.severity.disabled = true;
        elements.button.textContent = "Retry same alert";
        if (payload.latitude === null) {
            elements.latitude.textContent = "Latitude: Not provided";
            elements.longitude.textContent = "Longitude: Not provided";
            elements.accuracy.textContent = "Accuracy: Not available";
        } else {
            elements.latitude.textContent = `Latitude: ${payload.latitude}`;
            elements.longitude.textContent = `Longitude: ${payload.longitude}`;
            elements.accuracy.textContent = payload.location_accuracy_m === null
                ? "Accuracy: Not reported"
                : `Estimated accuracy: within ${Math.round(payload.location_accuracy_m)} m`;
        }
        setStatus(
            "A previous alert was not confirmed. Press SOS to safely retry the exact same submission."
        );
    } else if (pendingAttemptCorrupt) {
        elements.button.disabled = true;
        elements.severity.disabled = true;
    }
})();
