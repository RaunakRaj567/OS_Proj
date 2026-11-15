/* api.js — thin wrapper around the Flask REST API */
const API = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(url + " → " + r.status);
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r;
  },
  scenarios: () => API.get("/api/scenarios"),
  scenario: (id) => API.get("/api/scenarios/" + encodeURIComponent(id)),
  random: () => API.get("/api/random"),
  analyze: async (state) => (await API.post("/api/analyze", { state })).json(),                       // characterization + detection + safety
  prevent: async (state) => (await API.post("/api/prevent", { state })).json(),                       // prevention
  bankers: async (state, process, vector) =>
    (await API.post("/api/bankers/request", { state, process, request_vector: vector })).json(),      // avoidance
  resolve: async (state, history) => (await API.post("/api/resolve", { state, history })).json(),     // core: suggested resolutions
  trace: async (text) => (await API.post("/api/trace", { text })).json(),                            // core: process trace monitor
  recover: async (state, history) => (await API.post("/api/recover", { state, history })).json(),     // recovery
  starvation: async (state, rounds) => (await API.post("/api/starvation", { state, rounds })).json(), // starvation
  report: async (state, title, history) => API.post("/api/report", { state, title, history }),
};
