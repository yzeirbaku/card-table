// Overwritten at deploy time (Cloudflare Pages). Locally the backend runs on port 8020
// of whatever host served this page, so a phone on the Wi-Fi needs no setup.
window.BACKEND_URL = window.BACKEND_URL || `${location.protocol}//${location.hostname}:8020`;
