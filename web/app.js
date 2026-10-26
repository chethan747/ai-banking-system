/* AI Banking dashboard — plain JavaScript, no external libraries.
   Charts are drawn on <canvas> from real API data. */
(function () {
  "use strict";
  var token = localStorage.getItem("bank_token") || "";
  var user = null;
  try { user = JSON.parse(localStorage.getItem("bank_user") || "null"); } catch (e) { user = null; }

  function $(id) { return document.getElementById(id); }
  function money(n) { return "$" + Number(n || 0).toFixed(2); }
  function showMsg(text, isErr) {
    var el = $("msg"); el.textContent = text; el.hidden = false;
    el.className = isErr ? "msg err" : "msg";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
  }
  async function api(path, opts) {
    opts = opts || {};
    var res = await fetch(path, Object.assign({
      headers: {"Content-Type": "application/json",
                "Authorization": token ? "Bearer " + token : ""}
    }, opts));
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(data.error || ("Request failed: " + res.status));
    return data;
  }
  function txTable(txns) {
    if (!txns || !txns.length) return "<p>No transactions.</p>";
    var rows = txns.slice().reverse().map(function (t) {
      return "<tr><td>" + t.id + "</td><td>" + esc(t.type) + "</td><td>" +
        money(t.amount) + "</td><td>" + money(t.balance_after) + "</td><td>" +
        esc(t.description) + "</td><td>" + esc(t.timestamp) + "</td></tr>";
    }).join("");
    return "<table><tr><th>ID</th><th>Type</th><th>Amount</th><th>Balance after</th><th>Description</th><th>Time</th></tr>" + rows + "</table>";
  }
  function barChart(canvas, labels, values, color) {
    var ctx = canvas.getContext("2d"), w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    var max = Math.max.apply(null, values.concat([1]));
    var bw = w / Math.max(values.length, 1);
    values.forEach(function (v, i) {
      var bh = (v / max) * (h - 50);
      ctx.fillStyle = color || "#2563eb";
      ctx.fillRect(i * bw + 8, h - 30 - bh, bw - 16, bh);
      ctx.fillStyle = "#14213d"; ctx.font = "11px sans-serif"; ctx.textAlign = "center";
      ctx.fillText(money(v), i * bw + bw / 2, h - 34 - bh);
      ctx.fillText(String(labels[i]).slice(0, 12), i * bw + bw / 2, h - 12);
    });
  }
  function lineChart(canvas, values) {
    var ctx = canvas.getContext("2d"), w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    if (values.length < 2) { ctx.fillText("Not enough data yet.", 12, 20); return; }
    var max = Math.max.apply(null, values), min = Math.min.apply(null, values);
    var span = (max - min) || 1;
    ctx.beginPath();
    values.forEach(function (v, i) {
      var x = 10 + i * (w - 20) / (values.length - 1);
      var y = h - 20 - ((v - min) / span) * (h - 50);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#0ea5a4"; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = "#14213d"; ctx.font = "12px sans-serif";
    ctx.fillText("Latest: " + money(values[values.length - 1]), 12, 18);
    ctx.fillText("Range: " + money(min) + " – " + money(max), 12, 34);
  }

  async function loadDashboard() {
    var acc = await api("/api/accounts");
    var accounts = acc.accounts || [];
    var total = accounts.reduce(function (s, a) { return s + Number(a.balance); }, 0);
    var fraud = {flagged_count: 0};
    try { fraud = await api("/api/fraud/review"); } catch (e) { /* customers cannot see queue */ }
    var loans = await api("/api/loans");
    var pending = (loans.loans || []).filter(function (l) { return l.status === "pending"; }).length;
    $("summaryCards").innerHTML =
      '<div class="card"><div class="label">Total balance</div><div class="value">' + money(total) + "</div></div>" +
      '<div class="card"><div class="label">Accounts</div><div class="value">' + accounts.length + "</div></div>" +
      '<div class="card warn"><div class="label">Flagged transactions</div><div class="value">' + (fraud.flagged_count || 0) + "</div></div>" +
      '<div class="card"><div class="label">Loans in pipeline</div><div class="value">' + pending + " pending</div></div>";
    var insights = await api("/api/insights");
    $("insightsText").textContent = (insights.insights || []).join(" ");
    var cats = Object.keys(insights.totals_by_category || {}).filter(function (c) { return c !== "salary"; });
    barChart($("chartCategory"), cats, cats.map(function (c) { return insights.totals_by_category[c]; }));
    // Balance over time + recent transactions from all visible accounts.
    var allTx = [];
    for (var i = 0; i < accounts.length; i++) {
      var r = await api("/api/accounts/" + accounts[i].id + "/transactions");
      allTx = allTx.concat(r.transactions || []);
    }
    allTx.sort(function (a, b) { return String(a.timestamp).localeCompare(String(b.timestamp)); });
    lineChart($("chartBalance"), allTx.map(function (t) { return Number(t.balance_after); }));
    $("recentTx").innerHTML = txTable(allTx.slice(-10));
    var perDate = {};
    (fraud.flagged || []).forEach(function (f) {
      var d = String(f.transaction.timestamp || "").slice(0, 10) || "undated";
      perDate[d] = (perDate[d] || 0) + 1;
    });
    var dates = Object.keys(perDate).sort();
    barChart($("chartFraud"), dates.length ? dates : ["no flags"], dates.length ? dates.map(function (d) { return perDate[d]; }) : [0], "#dc2626");
  }

  async function loadAccounts() {
    var acc = await api("/api/accounts");
    var rows = (acc.accounts || []).map(function (a) {
      return "<tr><td>" + a.id + "</td><td>" + esc(a.customer_name || "") + "</td><td>" +
        esc(a.account_type) + "</td><td>" + esc(a.account_number) + "</td><td>" +
        money(a.balance) + "</td><td>" + esc(a.status) + "</td></tr>";
    }).join("");
    $("accountsTable").innerHTML = "<table><tr><th>ID</th><th>Customer</th><th>Type</th><th>Account no.</th><th>Balance</th><th>Status</th></tr>" + rows + "</table>";
    if (user && user.customer_id) $("newCustId").value = user.customer_id;
  }
  async function loadLoans() {
    var data = await api("/api/loans");
    var isMgr = user && (user.role === "manager" || user.role === "admin");
    var rows = (data.loans || []).map(function (l) {
      var btns = "";
      if (isMgr && l.status === "pending") {
        btns = '<button class="btn ok" data-review="' + l.id + '" data-decision="approve">Approve</button> ' +
          '<button class="btn danger" data-review="' + l.id + '" data-decision="reject">Reject</button>';
      }
      return "<tr><td>" + l.id + "</td><td>" + l.customer_id + "</td><td>" + money(l.amount) +
        "</td><td>" + esc(l.purpose) + "</td><td>" + l.term_months + "</td><td>" + esc(l.status) +
        "</td><td>" + btns + "</td></tr>";
    }).join("");
    $("loansTable").innerHTML = "<table><tr><th>ID</th><th>Customer</th><th>Amount</th><th>Purpose</th><th>Term</th><th>Status</th><th>Action</th></tr>" + rows + "</table>";
    document.querySelectorAll("[data-review]").forEach(function (b) {
      b.onclick = async function () {
        try {
          await api("/api/loans/" + b.dataset.review + "/review", {method: "POST",
            body: JSON.stringify({decision: b.dataset.decision})});
          showMsg("Loan " + b.dataset.review + " " + b.dataset.decision + "d.");
          loadLoans();
        } catch (e) { showMsg(e.message, true); }
      };
    });
  }
  async function loadFraud() {
    var data = await api("/api/fraud/review");
    var rows = (data.flagged || []).map(function (f) {
      var t = f.transaction;
      return "<tr><td>" + t.id + "</td><td>" + money(t.amount) + "</td><td class='flag'>" + f.score +
        "</td><td>" + esc(f.reasons.join("; ")) + "</td></tr>";
    }).join("");
    $("fraudTable").innerHTML = "<p>Flagged: " + data.flagged_count + "</p><table><tr><th>Txn ID</th><th>Amount</th><th>Score</th><th>Reasons</th></tr>" + rows + "</table>";
  }
  async function loadManagement() {
    try {
      var rep = await api("/api/reports");
      $("reportsBox").innerHTML = '<div class="panel"><h3>Totals</h3><pre>' +
        esc(JSON.stringify(rep.totals, null, 2)) + "</pre><h3>Flagged</h3><pre>" +
        esc(JSON.stringify(rep.flagged, null, 2)) + "</pre><h3>Loan pipeline</h3><pre>" +
        esc(JSON.stringify(rep.loan_pipeline, null, 2)) + "</pre></div>";
    } catch (e) { $("reportsBox").innerHTML = "<p>" + esc(e.message) + "</p>"; }
    var kyc = await api("/api/kyc");
    $("kycTable").innerHTML = "<table><tr><th>ID</th><th>Name</th><th>Status</th></tr>" +
      (kyc.records || []).map(function (r) { return "<tr><td>" + r.id + "</td><td>" + esc(r.name) + "</td><td>" + esc(r.kyc_status) + "</td></tr>"; }).join("") + "</table>";
    var aud = await api("/api/audit");
    $("auditTable").innerHTML = "<p>Chain valid: " + aud.chain_valid + " (" + aud.events.length + " events)</p><table><tr><th>ID</th><th>Actor</th><th>Action</th><th>Details</th></tr>" +
      aud.events.slice(-30).map(function (e) { return "<tr><td>" + e.id + "</td><td>" + esc(e.actor) + "</td><td>" + esc(e.action) + "</td><td>" + esc(e.details) + "</td></tr>"; }).join("") + "</table>";
  }

  function showView(name) {
    document.querySelectorAll(".view").forEach(function (v) { v.classList.remove("active"); });
    var el = $("view-" + name); if (el) el.classList.add("active");
    document.querySelectorAll("#nav button").forEach(function (b) {
      b.classList.toggle("active", b.dataset.view === name);
    });
    var loaders = {dashboard: loadDashboard, accounts: loadAccounts, loans: loadLoans,
      fraud: loadFraud, management: loadManagement};
    if (loaders[name]) loaders[name]().catch(function (e) { showMsg(e.message, true); });
  }
  function applyRoleGating() {
    document.querySelectorAll("#nav button[data-role]").forEach(function (b) {
      b.hidden = !(user && b.dataset.role.split(" ").indexOf(user.role) >= 0);
    });
    $("who").textContent = user ? (user.username + " (" + user.role + ")") : "";
  }
  function showApp() {
    $("loginView").hidden = true; $("appView").hidden = false;
    applyRoleGating(); showView("dashboard");
  }

  $("loginForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    try {
      var data = await api("/api/login", {method: "POST", body: JSON.stringify({
        username: $("username").value, password: $("password").value})});
      token = data.token; user = {username: data.username, role: data.role, customer_id: data.customer_id};
      localStorage.setItem("bank_token", token);
      localStorage.setItem("bank_user", JSON.stringify(user));
      showApp();
    } catch (err) {
      var el = $("loginError"); el.textContent = err.message; el.hidden = false;
    }
  });
  $("logoutBtn").onclick = function () {
    token = ""; user = null;
    localStorage.removeItem("bank_token"); localStorage.removeItem("bank_user");
    $("appView").hidden = true; $("loginView").hidden = false;
  };
  document.querySelectorAll("#nav button").forEach(function (b) {
    b.onclick = function () { showView(b.dataset.view); };
  });
  $("askForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    try { var d = await api("/api/assistant/ask", {method: "POST", body: JSON.stringify({question: $("question").value})});
      $("askAnswer").textContent = d.answer + (d.sources.length ? " (Source: " + d.sources.join(", ") + ")" : ""); }
    catch (err) { $("askAnswer").textContent = err.message; }
  });
  $("newAccountForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    try { await api("/api/accounts", {method: "POST", body: JSON.stringify({customer_id: Number($("newCustId").value), account_type: $("newAcctType").value, initial_balance: Number($("newBalance").value)})});
      showMsg("Account created."); loadAccounts(); } catch (err) { showMsg(err.message, true); }
  });
  var moneyKind = "deposit";
  document.querySelectorAll("#moneyForm button").forEach(function (b) {
    b.addEventListener("click", function () { moneyKind = b.dataset.kind; });
  });
  $("moneyForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    try { await api("/api/accounts/" + $("moneyAcct").value + "/" + moneyKind, {method: "POST", body: JSON.stringify({amount: Number($("moneyAmt").value), description: $("moneyDesc").value})});
      showMsg(moneyKind + " done."); loadAccounts(); loadDashboard(); } catch (err) { showMsg(err.message, true); }
  });
  $("loadTxBtn").onclick = async function () {
    try { var d = await api("/api/accounts/" + $("txAcct").value + "/transactions");
      $("txTable").innerHTML = txTable(d.transactions); } catch (err) { showMsg(err.message, true); }
  };
  $("loadStatementBtn").onclick = async function () {
    try { var now = new Date();
      var d = await api("/api/accounts/" + $("txAcct").value + "/statement?year=" + now.getFullYear() + "&month=" + (now.getMonth() + 1));
      $("statementBox").innerHTML = '<div class="panel"><h3>Statement ' + d.year + "-" + d.month + "</h3><p>Opening " + money(d.opening_balance) + " &middot; Closing " + money(d.closing_balance) + " &middot; In " + money(d.total_in) + " &middot; Out " + money(d.total_out) + "</p></div>"; }
    catch (err) { showMsg(err.message, true); }
  };
  $("transferForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    try { await api("/api/transfers", {method: "POST", body: JSON.stringify({from_id: Number($("fromId").value), to_id: Number($("toId").value), amount: Number($("transferAmt").value), description: $("transferDesc").value})});
      showMsg("Transfer done."); } catch (err) { showMsg(err.message, true); }
  });
  $("refreshFraudBtn").onclick = function () { loadFraud().catch(function (e) { showMsg(e.message, true); }); };
  $("fraudForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    var hist = $("fraudHist").value.split(",").map(function (s) { return {amount: Number(s.trim())}; }).filter(function (t) { return t.amount > 0; });
    try { var d = await api("/api/fraud/score", {method: "POST", body: JSON.stringify({transaction: {amount: Number($("fraudAmt").value)}, history: hist})});
      $("fraudResult").textContent = "Score " + d.score + ", flagged: " + d.flagged + ". " + d.reasons.join(" "); }
    catch (err) { $("fraudResult").textContent = err.message; }
  });
  $("loanForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    try { await api("/api/loans", {method: "POST", body: JSON.stringify({customer_id: Number($("loanCust").value), amount: Number($("loanAmt").value), purpose: $("loanPurpose").value, term_months: Number($("loanTerm").value)})});
      showMsg("Loan application submitted."); loadLoans(); } catch (err) { showMsg(err.message, true); }
  });
  $("creditForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    try { var d = await api("/api/credit/score", {method: "POST", body: JSON.stringify({features: {income: Number($("crIncome").value), monthly_debt: Number($("crDebt").value), employment_years: Number($("crYears").value), past_defaults: Number($("crDefaults").value), open_loans: Number($("crLoans").value), savings_balance: Number($("crSavings").value)}})});
      $("creditResult").textContent = "Score " + d.score + " (" + d.band + "). " + d.reasons.join(" "); }
    catch (err) { $("creditResult").textContent = err.message; }
  });
  $("kycForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    try { await api("/api/kyc", {method: "POST", body: JSON.stringify({name: $("kycName").value, email: $("kycEmail").value, dob: $("kycDob").value, address: $("kycAddr").value, id_type: $("kycType").value, id_number: $("kycId").value})});
      showMsg("KYC record added (ID stored as hash only)."); loadManagement(); } catch (err) { showMsg(err.message, true); }
  });

  if (token && user) showApp();
})();
