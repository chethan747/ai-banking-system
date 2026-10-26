/* AI Banking System - LIVE BROWSER DEMO (static, no server).
   DEMO ONLY - no real money, no real people, no real accounts.
   AI scores are illustrative, not regulated credit decisions. Not a production bank.
   Zero external dependencies. State lives in one localStorage key. */
(function () {
  'use strict';
  var STORAGE_KEY = 'aiBankingDemoV1';
  var FLAGGED_AT = 70;

  function money(n) {
    return '$' + Number(n).toFixed(2);
  }
  function fmtDate(ts) {
    var d = new Date(ts);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  function dayKey(ts) {
    var d = new Date(ts);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function daysAgo(days, hour, minute) {
    var d = new Date();
    d.setDate(d.getDate() - days);
    d.setHours(hour || 10, minute || 0, 0, 0);
    return d.getTime();
  }

  /* ---------- Pure logic (also exported for headless checks) ---------- */
  function typicalAmount(priorTxns, accountId) {
    var vals = priorTxns.filter(function (t) { return t.accountId === accountId; })
      .map(function (t) { return Math.abs(t.amount); });
    if (!vals.length) return 0;
    var sum = vals.reduce(function (a, b) { return a + b; }, 0);
    return sum / vals.length;
  }

  // Transparent fraud rules. Returns {score, reasons, flagged}.
  function fraudScore(tx, priorTxns) {
    var reasons = [];
    var score = 0;
    var amount = Math.abs(tx.amount);
    var typical = typicalAmount(priorTxns, tx.accountId);
    if (typical > 0) {
      var ratio = amount / typical;
      if (ratio >= 5) { score += 50; reasons.push('Large amount: ' + money(amount) + ' is ' + ratio.toFixed(1) + 'x this account\'s typical ' + money(typical) + ' (+50)'); }
      else if (ratio >= 3) { score += 35; reasons.push('Large amount: ' + money(amount) + ' is ' + ratio.toFixed(1) + 'x this account\'s typical ' + money(typical) + ' (+35)'); }
      else if (ratio >= 2) { score += 20; reasons.push('Above-typical amount: ' + money(amount) + ' vs typical ' + money(typical) + ' (+20)'); }
    }
    var hour = new Date(tx.timestamp).getHours();
    if (hour >= 0 && hour <= 4) { score += 25; reasons.push('Unusual hour: transaction at hour ' + hour + ' (00:00-04:59) (+25)'); }
    var oneHour = 60 * 60 * 1000;
    var recent = priorTxns.filter(function (t) {
      return t.accountId === tx.accountId && tx.timestamp - t.timestamp >= 0 && tx.timestamp - t.timestamp <= oneHour;
    }).length;
    if (recent >= 5) { score += 35; reasons.push('High velocity: ' + recent + ' prior transactions on this account in the last hour (+35)'); }
    else if (recent >= 3) { score += 25; reasons.push('High velocity: ' + recent + ' prior transactions on this account in the last hour (+25)'); }
    if (score > 100) score = 100;
    if (!reasons.length) reasons.push('No fraud rule triggered.');
    return { score: score, reasons: reasons, flagged: score >= FLAGGED_AT };
  }

  function creditScore(input) {
    var income = Number(input.income) || 0;
    var debt = Number(input.debt) || 0;
    var years = Number(input.years) || 0;
    var defaults = Number(input.defaults) || 0;
    var savings = Number(input.savings) || 0;
    var reasons = [];
    var score = 500;
    if (income >= 100000) { score += 70; reasons.push('Income ' + money(income) + ' per year: +70'); }
    else if (income >= 60000) { score += 50; reasons.push('Income ' + money(income) + ' per year: +50'); }
    else if (income >= 30000) { score += 20; reasons.push('Income ' + money(income) + ' per year: +20'); }
    else { score -= 20; reasons.push('Income ' + money(income) + ' per year: -20'); }
    var monthlyIncome = income / 12;
    var dti = monthlyIncome > 0 ? debt / monthlyIncome : 1;
    if (dti < 0.2) { score += 70; reasons.push('Monthly debt-to-income ' + (dti * 100).toFixed(0) + '% (under 20%): +70'); }
    else if (dti < 0.35) { score += 40; reasons.push('Monthly debt-to-income ' + (dti * 100).toFixed(0) + '%: +40'); }
    else if (dti < 0.5) { reasons.push('Monthly debt-to-income ' + (dti * 100).toFixed(0) + '%: +0'); }
    else { score -= 50; reasons.push('Monthly debt-to-income ' + (dti * 100).toFixed(0) + '% (50% or more): -50'); }
    if (years >= 5) { score += 50; reasons.push('Employment ' + years + ' years: +50'); }
    else if (years >= 3) { score += 30; reasons.push('Employment ' + years + ' years: +30'); }
    else if (years >= 1) { score += 10; reasons.push('Employment ' + years + ' years: +10'); }
    else { score -= 20; reasons.push('Employment under 1 year: -20'); }
    if (defaults === 0) { score += 60; reasons.push('No past defaults: +60'); }
    else if (defaults === 1) { score -= 60; reasons.push('1 past default: -60'); }
    else if (defaults === 2) { score -= 100; reasons.push('2 past defaults: -100'); }
    else { score -= 140; reasons.push(defaults + ' past defaults: -140'); }
    if (savings >= 15000) { score += 60; reasons.push('Savings ' + money(savings) + ': +60'); }
    else if (savings >= 5000) { score += 40; reasons.push('Savings ' + money(savings) + ': +40'); }
    else if (savings >= 1000) { score += 20; reasons.push('Savings ' + money(savings) + ': +20'); }
    else if (savings > 0) { reasons.push('Savings under $1,000: +0'); }
    else { score -= 20; reasons.push('No savings balance entered: -20'); }
    if (score < 300) score = 300;
    if (score > 850) score = 850;
    var band = score < 580 ? 'Poor' : score < 670 ? 'Fair' : score < 740 ? 'Good' : 'Excellent';
    return { score: score, band: band, reasons: reasons };
  }

  function categorize(description) {
    var d = (description || '').toLowerCase();
    if (d.indexOf('grocery') !== -1 || d.indexOf('grocer') !== -1) return 'Groceries';
    if (d.indexOf('rent') !== -1) return 'Housing';
    if (d.indexOf('utilit') !== -1) return 'Utilities';
    if (d.indexOf('transfer') !== -1) return 'Transfers';
    if (d.indexOf('dining') !== -1 || d.indexOf('restaurant') !== -1 || d.indexOf('coffee') !== -1) return 'Dining';
    if (d.indexOf('transport') !== -1 || d.indexOf('fuel') !== -1 || d.indexOf('taxi') !== -1) return 'Transport';
    return 'Other';
  }

  // Chart data, all computed from live transactions - never constants.
  function spendingByCategory(transactions) {
    var totals = {};
    transactions.forEach(function (t) {
      if (t.amount >= 0) return; // spending = money out only
      var c = categorize(t.description);
      totals[c] = (totals[c] || 0) + Math.abs(t.amount);
    });
    return Object.keys(totals).sort().map(function (k) { return { category: k, total: Math.round(totals[k] * 100) / 100 }; });
  }
  function balanceOverTime(transactions) {
    var sorted = transactions.slice().sort(function (a, b) { return a.timestamp - b.timestamp; });
    var perAccount = {};
    var points = [];
    sorted.forEach(function (t) {
      perAccount[t.accountId] = (perAccount[t.accountId] || 0) + t.amount;
      var total = 0;
      Object.keys(perAccount).forEach(function (k) { total += perAccount[k]; });
      points.push({ date: dayKey(t.timestamp), timestamp: t.timestamp, total: Math.round(total * 100) / 100 });
    });
    return points;
  }
  function fraudTrend(transactions) {
    var totals = {};
    transactions.forEach(function (t) {
      var k = dayKey(t.timestamp);
      if (!(k in totals)) totals[k] = 0;
      if (t.fraud && t.fraud.flagged) totals[k] += 1;
    });
    return Object.keys(totals).sort().map(function (k) { return { date: k, flagged: totals[k] }; });
  }
  function summaryStats(state) {
    var total = state.accounts.reduce(function (a, c) { return a + c.balance; }, 0);
    var flagged = state.transactions.filter(function (t) { return t.fraud && t.fraud.flagged; }).length;
    var weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
    var recent = state.transactions.filter(function (t) { return t.timestamp >= weekAgo; }).length;
    return { totalBalance: Math.round(total * 100) / 100, accountCount: state.accounts.length, transactionCount: state.transactions.length, recentCount: recent, flaggedCount: flagged, loanCount: state.loans.length, pendingLoans: state.loans.filter(function (l) { return l.status === 'pending'; }).length };
  }

  // Pure balance operations used by the UI and by headless checks.
  function applyDeposit(accounts, transactions, accountId, amount, description, timestamp) {
    if (!(amount > 0)) return { ok: false, error: 'Amount must be positive.' };
    var acc = accounts.filter(function (a) { return a.id === accountId; })[0];
    if (!acc) return { ok: false, error: 'Account not found.' };
    var tx = { id: 'tx-' + (timestamp || Date.now()), accountId: accountId, type: 'deposit', amount: amount, description: description || 'Deposit', timestamp: timestamp || Date.now(), balanceAfter: 0, fraud: null };
    tx.fraud = fraudScore(tx, transactions);
    acc.balance = Math.round((acc.balance + amount) * 100) / 100;
    tx.balanceAfter = acc.balance;
    transactions.push(tx);
    return { ok: true, transaction: tx };
  }
  function applyWithdrawal(accounts, transactions, accountId, amount, description, timestamp) {
    if (!(amount > 0)) return { ok: false, error: 'Amount must be positive.' };
    var acc = accounts.filter(function (a) { return a.id === accountId; })[0];
    if (!acc) return { ok: false, error: 'Account not found.' };
    if (amount > acc.balance) return { ok: false, error: 'Insufficient funds: balance is ' + money(acc.balance) + '.' };
    var tx = { id: 'tx-' + (timestamp || Date.now()), accountId: accountId, type: 'withdrawal', amount: -amount, description: description || 'Withdrawal', timestamp: timestamp || Date.now(), balanceAfter: 0, fraud: null };
    tx.fraud = fraudScore(tx, transactions);
    acc.balance = Math.round((acc.balance - amount) * 100) / 100;
    tx.balanceAfter = acc.balance;
    transactions.push(tx);
    return { ok: true, transaction: tx };
  }
  function applyTransfer(accounts, transactions, fromId, toId, amount, description, timestamp) {
    if (fromId === toId) return { ok: false, error: 'Cannot transfer to the same account.' };
    if (!(amount > 0)) return { ok: false, error: 'Amount must be positive.' };
    var from = accounts.filter(function (a) { return a.id === fromId; })[0];
    var to = accounts.filter(function (a) { return a.id === toId; })[0];
    if (!from || !to) return { ok: false, error: 'Account not found.' };
    if (amount > from.balance) return { ok: false, error: 'Insufficient funds: balance is ' + money(from.balance) + '.' };
    var ts = timestamp || Date.now();
    var out = applyWithdrawal(accounts, transactions, fromId, amount, description || ('Transfer to ' + to.name), ts);
    if (!out.ok) return out;
    var inn = applyDeposit(accounts, transactions, toId, amount, description || ('Transfer from ' + from.name), ts + 1);
    if (!inn.ok) { // roll back (atomicity for the demo)
      from.balance = Math.round((from.balance + amount) * 100) / 100;
      transactions.pop();
      return inn;
    }
    return { ok: true, out: out.transaction, in: inn.transaction };
  }

  var LOGIC = { STORAGE_KEY: STORAGE_KEY, FLAGGED_AT: FLAGGED_AT, money: money, typicalAmount: typicalAmount, fraudScore: fraudScore, creditScore: creditScore, categorize: categorize, spendingByCategory: spendingByCategory, balanceOverTime: balanceOverTime, fraudTrend: fraudTrend, summaryStats: summaryStats, applyDeposit: applyDeposit, applyWithdrawal: applyWithdrawal, applyTransfer: applyTransfer };
  if (typeof module !== 'undefined' && module.exports) { module.exports = LOGIC; }
  if (typeof window !== 'undefined') { window.AIBanking = LOGIC; }
  if (typeof document === 'undefined') return; // headless: logic only, no DOM

  /* ---------- Seed data (fictitious people only) ---------- */
  function seedState() {
    var txns = [];
    function seedTx(accountId, type, amount, description, ts, balanceAfter) {
      var tx = { id: 'seed-' + txns.length, accountId: accountId, type: type, amount: amount, description: description, timestamp: ts, balanceAfter: balanceAfter, fraud: null };
      tx.fraud = fraudScore(tx, txns);
      txns.push(tx);
    }
    seedTx('checking', 'deposit', 2600, 'Paycheck deposit', daysAgo(10, 9, 0), 2600);
    seedTx('checking', 'withdrawal', -85.40, 'Grocery store', daysAgo(9, 12, 30), 2514.60);
    seedTx('checking', 'withdrawal', -950, 'Rent payment', daysAgo(8, 10, 0), 1564.60);
    seedTx('checking', 'deposit', 450, 'Freelance payment', daysAgo(6, 14, 0), 2014.60);
    seedTx('checking', 'withdrawal', -139.40, 'Utilities bill', daysAgo(4, 11, 0), 1875.20);
    seedTx('savings', 'deposit', 7500, 'Opening deposit', daysAgo(12, 9, 0), 7500);
    seedTx('savings', 'deposit', 400, 'Transfer from checking', daysAgo(5, 10, 0), 7900);
    seedTx('savings', 'deposit', 275, 'Bonus deposit', daysAgo(3, 15, 0), 8175);
    seedTx('savings', 'deposit', 25, 'Interest credit', daysAgo(2, 9, 0), 8200);
    return {
      role: 'customer',
      accounts: [
        { id: 'checking', name: 'Demo Checking', owner: 'Demo User', type: 'checking', balance: 1875.20 },
        { id: 'savings', name: 'Demo Savings', owner: 'Demo User', type: 'savings', balance: 8200 }
      ],
      transactions: txns,
      loans: [
        { id: 'loan-1', applicant: 'Alex Demo', purpose: 'Home improvement', amount: 12000, status: 'pending' },
        { id: 'loan-2', applicant: 'Priya Demo', purpose: 'Small business equipment', amount: 25000, status: 'pending' },
        { id: 'loan-3', applicant: 'Sam Demo', purpose: 'Vehicle purchase', amount: 18000, status: 'pending' }
      ]
    };
  }
  function loadState() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw) { var parsed = JSON.parse(raw); if (parsed && parsed.accounts && parsed.transactions && parsed.loans) return parsed; }
    } catch (e) { /* fall through to seed */ }
    var s = seedState();
    saveState(s);
    return s;
  }
  function saveState(s) { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); } catch (e) { /* storage unavailable */ } }

  var state = loadState();
  var currentTab = 'dashboard';
  var detailAccountId = 'checking';
  var historyFilter = 'all';

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function accountName(id) { var a = state.accounts.filter(function (x) { return x.id === id; })[0]; return a ? a.name : id; }
  function sortedTxns() { return state.transactions.slice().sort(function (a, b) { return b.timestamp - a.timestamp; }); }
  function txRow(t) {
    var flag = t.fraud && t.fraud.flagged ? '<span class="badge flagged">FLAGGED ' + t.fraud.score + '</span>' : '<span class="badge ok">' + (t.fraud ? t.fraud.score : 0) + '</span>';
    return '<tr><td>' + fmtDate(t.timestamp) + '</td><td>' + esc(accountName(t.accountId)) + '</td><td>' + esc(t.type) + '</td><td>' + esc(t.description) + '</td><td>' + money(t.amount) + '</td><td>' + money(t.balanceAfter) + '</td><td>' + flag + '</td></tr>';
  }

  /* ---------- Canvas charts (plain canvas only) ---------- */
  function setupCanvas(canvas) {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 600, h = 220;
    canvas.width = w * dpr; canvas.height = h * dpr;
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h };
  }
  function drawBars(canvas, labels, values, color) {
    if (!canvas) return;
    var s = setupCanvas(canvas), ctx = s.ctx;
    ctx.clearRect(0, 0, s.w, s.h);
    ctx.fillStyle = '#e2e8f0'; ctx.font = '11px system-ui, sans-serif';
    if (!values.length || Math.max.apply(null, values) === 0) { ctx.fillText('No data yet - add a transaction to see this chart.', 12, 30); return; }
    var max = Math.max.apply(null, values);
    var barW = Math.min(48, (s.w - 20) / values.length * 0.6);
    var gap = (s.w - 20) / values.length;
    values.forEach(function (v, i) {
      var bh = max ? (v / max) * (s.h - 60) : 0;
      var x = 10 + i * gap + (gap - barW) / 2;
      ctx.fillStyle = color || '#38bdf8';
      ctx.fillRect(x, s.h - 36 - bh, barW, bh);
      ctx.fillStyle = '#e2e8f0'; ctx.textAlign = 'center';
      ctx.fillText(money(v), x + barW / 2, s.h - 40 - bh);
      var lab = String(labels[i]).slice(0, 12);
      ctx.fillText(lab, x + barW / 2, s.h - 18);
      ctx.textAlign = 'left';
    });
  }
  function drawLine(canvas, points) {
    if (!canvas) return;
    var s = setupCanvas(canvas), ctx = s.ctx;
    ctx.clearRect(0, 0, s.w, s.h);
    ctx.fillStyle = '#e2e8f0'; ctx.font = '11px system-ui, sans-serif';
    if (points.length < 2) { ctx.fillText('Need at least two transactions to draw a balance line.', 12, 30); return; }
    var vals = points.map(function (p) { return p.total; });
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var range = (max - min) || 1;
    ctx.strokeStyle = '#38bdf8'; ctx.lineWidth = 2; ctx.beginPath();
    points.forEach(function (p, i) {
      var x = 14 + i * (s.w - 28) / (points.length - 1);
      var y = s.h - 36 - ((p.total - min) / range) * (s.h - 70);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = '#e2e8f0';
    ctx.fillText(money(min) + ' (low)', 12, s.h - 18);
    ctx.fillText(money(max) + ' (high)', s.w - 130, s.h - 18);
    ctx.fillText('Latest: ' + money(points[points.length - 1].total) + ' on ' + points[points.length - 1].date, 12, 20);
  }
  function renderCharts() {
    var spend = spendingByCategory(state.transactions);
    drawBars($('chart-spending'), spend.map(function (x) { return x.category; }), spend.map(function (x) { return x.total; }), '#38bdf8');
    drawLine($('chart-balance'), balanceOverTime(state.transactions));
    var trend = fraudTrend(state.transactions);
    drawBars($('chart-fraud'), trend.map(function (x) { return x.date.slice(5); }), trend.map(function (x) { return x.flagged; }), '#ef4444');
    var cap = $('chart-spending-caption');
    if (cap) cap.textContent = spend.length ? spend.map(function (x) { return x.category + ' ' + money(x.total); }).join('  |  ') : 'No spending yet.';
  }

  /* ---------- Render ---------- */
  function render() {
    var isManager = state.role === 'manager';
    document.querySelectorAll('.role-switch button').forEach(function (b) { b.classList.toggle('active', b.dataset.role === state.role); });
    document.querySelectorAll('nav button').forEach(function (b) { b.classList.toggle('active', b.dataset.tab === currentTab); });
    document.querySelectorAll('.view').forEach(function (v) { v.classList.toggle('active', v.id === 'view-' + currentTab); });
    var sum = summaryStats(state);
    $('stat-balance').textContent = money(sum.totalBalance);
    $('stat-accounts').textContent = String(sum.accountCount);
    $('stat-recent').textContent = String(sum.recentCount) + ' in last 7 days';
    $('stat-flagged').textContent = String(sum.flaggedCount);
    $('stat-loans').textContent = String(sum.pendingLoans) + ' pending / ' + sum.loanCount + ' total';
    $('mgmt-totals').innerHTML = '<p><strong>Accounts:</strong> ' + sum.accountCount + ' &nbsp; <strong>Total balance:</strong> ' + money(sum.totalBalance) + ' &nbsp; <strong>Transactions:</strong> ' + sum.transactionCount + ' &nbsp; <strong>Flagged:</strong> ' + sum.flaggedCount + '</p>';
    // Accounts
    $('account-cards').innerHTML = state.accounts.map(function (a) {
      return '<div class="card"><h3>' + esc(a.name) + '</h3><div class="balance">' + money(a.balance) + '</div><p class="muted">' + esc(a.type) + ' - ' + esc(a.owner) + '</p><button class="account-btn secondary" data-account="' + a.id + '">View history</button></div>';
    }).join('');
    document.querySelectorAll('[data-account]').forEach(function (b) { b.onclick = function () { detailAccountId = b.dataset.account; $('detail-account').value = detailAccountId; renderDetail(); }; });
    // Detail + selects
    var opts = '<option value="all">All accounts</option>' + state.accounts.map(function (a) { return '<option value="' + a.id + '">' + esc(a.name) + '</option>'; }).join('');
    $('history-filter').innerHTML = opts;
    $('history-filter').value = historyFilter;
    $('detail-account').innerHTML = state.accounts.map(function (a) { return '<option value="' + a.id + '">' + esc(a.name) + '</option>'; }).join('');
    $('detail-account').value = detailAccountId;
    $('deposit-account').innerHTML = state.accounts.map(function (a) { return '<option value="' + a.id + '">' + esc(a.name) + '</option>'; }).join('');
    $('withdraw-account').innerHTML = state.accounts.map(function (a) { return '<option value="' + a.id + '">' + esc(a.name) + '</option>'; }).join('');
    $('transfer-from').innerHTML = state.accounts.map(function (a) { return '<option value="' + a.id + '">' + esc(a.name) + '</option>'; }).join('');
    $('transfer-to').innerHTML = state.accounts.map(function (a) { return '<option value="' + a.id + '">' + esc(a.name) + '</option>'; }).join('');
    renderDetail();
    renderHistory();
    renderFraud();
    renderLoans();
    renderCharts();
    $('gate-note').style.display = isManager ? 'none' : 'block';
    $('fraud-gate').style.display = isManager ? 'none' : 'block';
    $('fraud-table-wrap').style.display = isManager ? 'block' : 'none';
    $('mgmt-gate').style.display = isManager ? 'none' : 'block';
    $('mgmt-content').style.display = isManager ? 'block' : 'none';
    var recent = sortedTxns().slice(0, 5);
    $('recent-table').innerHTML = recent.length ? recent.map(txRow).join('') : '<tr><td colspan="7">No transactions yet.</td></tr>';
  }
  function renderDetail() {
    var acc = state.accounts.filter(function (a) { return a.id === detailAccountId; })[0] || state.accounts[0];
    if (!acc) return;
    $('detail-info').innerHTML = '<h3>' + esc(acc.name) + '</h3><div class="balance">' + money(acc.balance) + '</div><p class="muted">' + esc(acc.type) + ' - ' + esc(acc.owner) + '</p>';
    var rows = state.transactions.filter(function (t) { return t.accountId === acc.id; }).sort(function (a, b) { return b.timestamp - a.timestamp; });
    $('detail-table').innerHTML = rows.length ? rows.map(txRow).join('') : '<tr><td colspan="7">No transactions for this account.</td></tr>';
  }
  function renderHistory() {
    var rows = sortedTxns().filter(function (t) { return historyFilter === 'all' || t.accountId === historyFilter; });
    $('history-table').innerHTML = rows.length ? rows.map(txRow).join('') : '<tr><td colspan="7">No transactions match this filter.</td></tr>';
  }
  function renderFraud() {
    var flagged = sortedTxns().filter(function (t) { return t.fraud && t.fraud.flagged; });
    $('fraud-count').textContent = String(flagged.length);
    $('fraud-table').innerHTML = flagged.length ? flagged.map(function (t) {
      return '<tr><td>' + fmtDate(t.timestamp) + '</td><td>' + esc(accountName(t.accountId)) + '</td><td>' + esc(t.description) + '</td><td>' + money(t.amount) + '</td><td><strong>' + t.fraud.score + '/100</strong></td><td>' + esc(t.fraud.reasons.join('; ')) + '</td></tr>';
    }).join('') : '<tr><td colspan="6">No flagged transactions. A transaction is flagged at a fraud score of 70 or more.</td></tr>';
    $('fraud-rules').innerHTML = '<li>Large amount vs typical amount for that account (2x: +20, 3x: +35, 5x or more: +50).</li><li>Unusual hour 00:00-04:59: +25.</li><li>High velocity: 3-4 prior transactions on the same account in the last hour: +25; 5 or more: +35.</li><li>Scores are capped at 100. Flagged at 70 or more.</li>';
  }
  function renderLoans() {
    var isManager = state.role === 'manager';
    $('loan-table').innerHTML = state.loans.map(function (l) {
      var actions = l.status === 'pending' && isManager
        ? '<button data-approve="' + l.id + '">Approve</button> <button class="danger" data-reject="' + l.id + '">Reject</button>'
        : '<span class="muted">No further review</span>';
      return '<tr><td>' + esc(l.applicant) + '</td><td>' + esc(l.purpose) + '</td><td>' + money(l.amount) + '</td><td><span class="badge ' + l.status + '">' + l.status + '</span></td><td>' + actions + '</td></tr>';
    }).join('');
    document.querySelectorAll('[data-approve]').forEach(function (b) { b.onclick = function () { setLoan(b.dataset.approve, 'approved'); }; });
    document.querySelectorAll('[data-reject]').forEach(function (b) { b.onclick = function () { setLoan(b.dataset.reject, 'rejected'); }; });
  }
  function setLoan(id, status) {
    var loan = state.loans.filter(function (l) { return l.id === id; })[0];
    if (!loan || loan.status !== 'pending') return;
    loan.status = status;
    saveState(state); render();
  }
  function showMsg(id, text, isError) {
    var el = $(id);
    el.textContent = text;
    el.className = 'msg' + (isError ? ' error' : '');
    el.style.display = 'block';
  }
  function afterTxn(result, msgId) {
    if (!result.ok) { showMsg(msgId, result.error, true); return; }
    saveState(state); render();
    showMsg(msgId, 'Done. New balance updated and transaction added to history.', false);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('nav button').forEach(function (b) { b.onclick = function () { currentTab = b.dataset.tab; render(); }; });
    document.querySelectorAll('.role-switch button').forEach(function (b) { b.onclick = function () { state.role = b.dataset.role; saveState(state); render(); }; });
    $('reset-btn').onclick = function () {
      if (!confirm('Reset the demo? This clears all demo changes and restores the seed data.')) return;
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* ignore */ }
      state = seedState(); saveState(state); historyFilter = 'all'; detailAccountId = 'checking'; render();
    };
    $('history-filter').onchange = function () { historyFilter = this.value; renderHistory(); };
    $('detail-account').onchange = function () { detailAccountId = this.value; renderDetail(); };
    $('deposit-form').onsubmit = function (e) {
      e.preventDefault();
      afterTxn(applyDeposit(state.accounts, state.transactions, $('deposit-account').value, parseFloat($('deposit-amount').value), $('deposit-desc').value || 'Deposit'), 'deposit-msg');
    };
    $('withdraw-form').onsubmit = function (e) {
      e.preventDefault();
      afterTxn(applyWithdrawal(state.accounts, state.transactions, $('withdraw-account').value, parseFloat($('withdraw-amount').value), $('withdraw-desc').value || 'Withdrawal'), 'withdraw-msg');
    };
    $('transfer-form').onsubmit = function (e) {
      e.preventDefault();
      var r = applyTransfer(state.accounts, state.transactions, $('transfer-from').value, $('transfer-to').value, parseFloat($('transfer-amount').value), $('transfer-desc').value || 'Internal transfer');
      afterTxn(r, 'transfer-msg');
    };
    $('credit-form').onsubmit = function (e) {
      e.preventDefault();
      var r = creditScore({ income: $('credit-income').value, debt: $('credit-debt').value, years: $('credit-years').value, defaults: $('credit-defaults').value, savings: $('credit-savings').value });
      $('credit-result').innerHTML = '<div class="score-big">' + r.score + ' - ' + r.band + '</div><p><strong>Illustrative only.</strong> This is not a regulated credit decision and does not use a real credit bureau score.</p><ul><li>' + r.reasons.map(esc).join('</li><li>') + '</li></ul>';
    };
    render();
    window.addEventListener('resize', renderCharts);
  });
})();
