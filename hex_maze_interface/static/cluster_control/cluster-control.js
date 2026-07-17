const prismCount = 7;
// One position request reads all seven motor controllers.  Ten updates per
// second is the practical ceiling for a responsive operator display while
// retaining headroom for the controller's motion and safety loop.
const positionPollIntervalMs = 100;
const minimumPositionPollTimeoutMs = 15000;
const positionPollGraceMs = 5000;

let connected = false;
let motionReady = false;
let busy = false;
let paused = false;
let commandedTargets = null;
let latestState = null;
let positionPollTimer = null;
let positionPollInFlight = false;
let positionPollDeadline = 0;

const clusterAddress = document.querySelector("#cluster-address");
const maxVelocity = document.querySelector("#max-velocity");
const status = document.querySelector("#status");
const buttons = {
  connect: document.querySelector("#connect"),
  home: document.querySelector("#home"),
  move: document.querySelector("#move"),
  refresh: document.querySelector("#refresh"),
  pause: document.querySelector("#pause"),
  powerOff: document.querySelector("#power-off"),
  quit: document.querySelector("#quit"),
};

const targetInputs = [];
const currentCells = [];
const statusCells = [];
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
  statusCells.push(row.children[3]);
  rows.append(row);
}

function updateButtons() {
  buttons.connect.disabled = busy;
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

function homeDescription(outcome) {
  const labels = {
    target_reached: "fixed-travel home complete",
    confirmed: "home confirmed",
    stall: "home stopped on StallGuard",
    in_progress: "homing",
    failed: "home failed",
    none: "not homed",
  };
  return labels[outcome] || outcome;
}

function diagnosticIssues(diagnostic) {
  if (!diagnostic) return [];
  const issues = [];
  if (!diagnostic.communicating) issues.push("not communicating");
  if (diagnostic.communication_failure_latched) issues.push("communication failure");
  if (diagnostic.reset_latched) issues.push("controller reset");
  if (diagnostic.driver_error_latched) issues.push("driver error");
  if (diagnostic.charge_pump_undervoltage_latched) issues.push("charge-pump undervoltage");
  if (diagnostic.recovery_failed_latched) issues.push("recovery failed");
  if (diagnostic.over_temperature_warning) issues.push("over-temperature warning");
  if (diagnostic.over_temperature_shutdown) issues.push("over-temperature shutdown");
  if (diagnostic.short_to_ground_a) issues.push("short to ground A");
  if (diagnostic.short_to_ground_b) issues.push("short to ground B");
  if (diagnostic.open_load_a) issues.push("open load A");
  if (diagnostic.open_load_b) issues.push("open load B");
  return issues;
}

function diagnosticNotes(diagnostic) {
  if (!diagnostic) return [];
  const notes = [];
  if (diagnostic.recovery_attempted_latched) notes.push("recovery attempted");
  if (diagnostic.mirror_resync_required) notes.push("mirror resync required");
  if (diagnostic.stallguard) notes.push("StallGuard active");
  return notes;
}

function prismStatus(state, index) {
  const diagnostic = state.diagnostics?.[index];
  const issues = diagnosticIssues(diagnostic);
  const notes = diagnosticNotes(diagnostic);
  const position = state.positions_mm[index];
  const outcome = state.home_outcomes[index];
  let text;

  if (issues.length > 0) {
    text = `Fault: ${issues.join(", ")}`;
  } else if (outcome === "in_progress") {
    text = "Homing";
  } else if (outcome === "failed") {
    text = "Home failed";
  } else if (!state.homed[index]) {
    text = diagnostic?.standstill ? "Not homed — at rest" : "Not homed — active";
  } else if (commandedTargets) {
    const target = commandedTargets[index];
    if (position === target) {
      text = `At target ${target} mm — ${homeDescription(outcome)}`;
    } else if (paused) {
      text = `Paused at ${position} mm (target ${target} mm)`;
    } else if (diagnostic?.standstill) {
      text = `Target pending at ${position} mm (target ${target} mm)`;
    } else {
      text = `Moving to ${target} mm`;
    }
  } else {
    text = diagnostic?.standstill
      ? `Ready — ${homeDescription(outcome)}`
      : `Active — ${homeDescription(outcome)}`;
  }

  return {
    text,
    detail: [homeDescription(outcome), ...issues, ...notes].join("; "),
  };
}

function renderPrismState() {
  if (!latestState) return;
  latestState.positions_mm.forEach((position, index) => {
    currentCells[index].textContent = position;
    const prism = prismStatus(latestState, index);
    statusCells[index].textContent = prism.text;
    statusCells[index].title = prism.detail;
  });
}

function showState(state) {
  latestState = state;
  maxVelocity.textContent = state.controller_parameters.max_velocity;
  renderPrismState();
}

function showPositions(positionsMm) {
  if (latestState) {
    latestState = { ...latestState, positions_mm: positionsMm };
    renderPrismState();
    return;
  }
  positionsMm.forEach((position, index) => {
    currentCells[index].textContent = position;
  });
}

function stopPositionPolling() {
  if (positionPollTimer !== null) {
    window.clearInterval(positionPollTimer);
    positionPollTimer = null;
  }
}

function targetsReached(positionsMm) {
  return commandedTargets !== null && positionsMm.every(
    (position, index) => position === commandedTargets[index],
  );
}

function positionPollTimeoutMs() {
  if (!latestState || !commandedTargets) return minimumPositionPollTimeoutMs;
  const maximumDistance = Math.max(...latestState.positions_mm.map(
    (position, index) => Math.abs(commandedTargets[index] - position),
  ));
  const velocity = Math.max(1, Number(latestState.controller_parameters.max_velocity));
  return Math.max(
    minimumPositionPollTimeoutMs,
    (maximumDistance / velocity) * 3000 + positionPollGraceMs,
  );
}

async function pollPositions() {
  if (!connected || busy || !commandedTargets || positionPollInFlight) return;
  if (Date.now() >= positionPollDeadline) {
    stopPositionPolling();
    status.textContent = "Stopped automatic updates before all targets were reached. Click Refresh.";
    return;
  }

  positionPollInFlight = true;
  try {
    const result = await request("/api/positions");
    showPositions(result.positions_mm);
    if (targetsReached(result.positions_mm)) {
      stopPositionPolling();
      const state = await request("/api/state");
      showState(state.state);
      status.textContent = "All prisms reached their targets.";
    }
  } catch (error) {
    stopPositionPolling();
    status.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    positionPollInFlight = false;
  }
}

function startPositionPolling() {
  stopPositionPolling();
  positionPollDeadline = Date.now() + positionPollTimeoutMs();
  void pollPositions();
  positionPollTimer = window.setInterval(() => {
    void pollPositions();
  }, positionPollIntervalMs);
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
  stopPositionPolling();
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
  paused = false;
  commandedTargets = null;
  showState(result.state);
  status.textContent = `Connected to cluster ${cluster}. Home all before commanding motion.`;
}));

buttons.home.addEventListener("click", () => run("Homing all prisms…", async () => {
  const result = await request("/api/home", { method: "POST" });
  motionReady = true;
  paused = false;
  commandedTargets = null;
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
  commandedTargets = positions;
  paused = false;
  showState(result.state);
  status.textContent = "Target positions sent. Updating current positions ten times per second.";
  startPositionPolling();
}));

buttons.refresh.addEventListener("click", () => run("Reading cluster state…", async () => {
  const result = await request("/api/state");
  showState(result.state);
  status.textContent = "Cluster state refreshed.";
}));

buttons.pause.addEventListener("click", () => run("Pausing…", async () => {
  const result = await request("/api/pause", { method: "POST" });
  motionReady = false;
  paused = true;
  showState(result.state);
  status.textContent = "Cluster paused. Home all before commanding another move.";
}));

buttons.powerOff.addEventListener("click", () => {
  if (!window.confirm("Turn off prism power for this cluster?")) return;
  run("Powering off…", async () => {
    const result = await request("/api/power-off", { method: "POST" });
    motionReady = false;
    paused = true;
    showState(result.state);
    status.textContent = "Prism power is off.";
  });
});

buttons.quit.addEventListener("click", () => run("Closing Cluster Control…", async () => {
  await request("/api/quit", { method: "POST" });
  status.textContent = "Cluster Control has closed.";
  window.close();
}));

window.addEventListener("beforeunload", stopPositionPolling);
updateButtons();
