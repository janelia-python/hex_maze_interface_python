const prismCount = 7;
let connected = false;
let motionReady = false;
let busy = false;

const clusterAddress = document.querySelector("#cluster-address");
const maxVelocity = document.querySelector("#max-velocity");
const status = document.querySelector("#status");
const buttons = {
  connect: document.querySelector("#connect"),
  velocity: document.querySelector("#apply-velocity"),
  home: document.querySelector("#home"),
  move: document.querySelector("#move"),
  refresh: document.querySelector("#refresh"),
  pause: document.querySelector("#pause"),
  powerOff: document.querySelector("#power-off"),
  quit: document.querySelector("#quit"),
};

const targetInputs = [];
const currentCells = [];
const homeCells = [];
const rows = document.querySelector("#prisms");
for (let index = 0; index < prismCount; index += 1) {
  const row = document.createElement("tr");
  row.innerHTML = `<td>${index + 1}</td><td></td><td>—</td><td>—</td>`;
  const target = document.createElement("input");
  target.type = "number";
  target.min = "0";
  target.max = "550";
  target.value = "0";
  target.inputMode = "numeric";
  row.children[1].append(target);
  targetInputs.push(target);
  currentCells.push(row.children[2]);
  homeCells.push(row.children[3]);
  rows.append(row);
}

function updateButtons() {
  buttons.connect.disabled = busy;
  buttons.velocity.disabled = !connected || busy;
  buttons.home.disabled = !connected || busy;
  buttons.refresh.disabled = !connected || busy;
  buttons.pause.disabled = !connected || busy;
  buttons.powerOff.disabled = !connected || busy;
  buttons.quit.disabled = busy;
  buttons.move.disabled = !connected || !motionReady || busy;
}

function setBusy(message) {
  busy = true;
  status.textContent = message;
  updateButtons();
}

function showState(state) {
  maxVelocity.value = state.controller_parameters.max_velocity;
  state.positions_mm.forEach((position, index) => {
    currentCells[index].textContent = position;
  });
  state.home_outcomes.forEach((outcome, index) => {
    homeCells[index].textContent = state.homed[index] ? `${outcome} (homed)` : outcome;
  });
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || "The cluster-control request failed.");
  }
  return body;
}

async function run(message, action) {
  setBusy(message);
  try {
    await action();
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    busy = false;
    updateButtons();
  }
}

buttons.connect.addEventListener("click", () => run("Connecting…", async () => {
  const cluster = Number(clusterAddress.value);
  const result = await request("/api/connect", {
    method: "POST",
    body: JSON.stringify({ cluster_address: cluster }),
  });
  connected = true;
  motionReady = false;
  showState(result.state);
  status.textContent = `Connected to cluster ${cluster}. Home all before commanding motion.`;
}));

buttons.velocity.addEventListener("click", () => run("Applying maximum velocity…", async () => {
  const result = await request("/api/max-velocity", {
    method: "POST",
    body: JSON.stringify({ max_velocity_mm_s: Number(maxVelocity.value) }),
  });
  showState(result.state);
  status.textContent = `Maximum velocity set to ${result.state.controller_parameters.max_velocity} mm/s.`;
}));

buttons.home.addEventListener("click", () => run("Homing all prisms…", async () => {
  const result = await request("/api/home", { method: "POST" });
  motionReady = true;
  showState(result.state);
  status.textContent = "All prisms completed homing. Motion is enabled.";
}));

buttons.move.addEventListener("click", () => run("Sending target positions…", async () => {
  const positions = targetInputs.map((input) => Number(input.value));
  if (positions.some((position) => !Number.isInteger(position))) {
    throw new Error("Every target position must be a whole number of millimetres.");
  }
  const result = await request("/api/move", {
    method: "POST",
    body: JSON.stringify({ positions_mm: positions }),
  });
  showState(result.state);
  status.textContent = "Target positions sent.";
}));

buttons.refresh.addEventListener("click", () => run("Reading cluster state…", async () => {
  const result = await request("/api/state");
  showState(result.state);
  status.textContent = "Cluster state refreshed.";
}));

buttons.pause.addEventListener("click", () => run("Pausing…", async () => {
  const result = await request("/api/pause", { method: "POST" });
  motionReady = false;
  showState(result.state);
  status.textContent = "Cluster paused. Home all before commanding another move.";
}));

buttons.powerOff.addEventListener("click", () => {
  if (!window.confirm("Turn off prism power for this cluster?")) return;
  run("Powering off…", async () => {
    const result = await request("/api/power-off", { method: "POST" });
    motionReady = false;
    showState(result.state);
    status.textContent = "Prism power is off.";
  });
});

buttons.quit.addEventListener("click", () => run("Closing Cluster Control…", async () => {
  await request("/api/quit", { method: "POST" });
  status.textContent = "Cluster Control has closed.";
  window.close();
}));

updateButtons();
