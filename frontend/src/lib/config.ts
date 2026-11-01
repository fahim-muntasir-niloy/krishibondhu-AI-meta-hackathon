/** The API. Same origin as the page wherever FastAPI serves the built frontend (main.py);
 * `next dev` runs apart from it, so there it is the API on :2024. */
const configured = process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "development" ? "http://localhost:2024" : "");

/** Absolute in the browser, for the voice socket. */
export const API_URL = !configured && typeof window !== "undefined" ? window.location.origin : configured;

export const PHONE_HEADER = "X-Phone-Number";

/** Sent with every API call. ngrok's free tier answers browser requests with an
 * HTML warning page unless this header is present; other hosts ignore it. */
export const API_HEADERS = { "ngrok-skip-browser-warning": "1" };
