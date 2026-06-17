PRAGMA foreign_keys = ON;

-- PDV/Caixa schema (usa tabelas existentes: orders, order_items, payments)
-- Este arquivo documenta o modelo e pode ser usado em bases novas.

CREATE TABLE IF NOT EXISTS cash_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opened_at TEXT NOT NULL DEFAULT (datetime('now')),
  closed_at TEXT,
  opening_cash_cents INTEGER NOT NULL DEFAULT 0,
  closing_cash_cents INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'OPEN',
  notes TEXT,
  operator_id INTEGER,
  store_id INTEGER
);

CREATE TABLE IF NOT EXISTS cash_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  type TEXT NOT NULL, -- IN / OUT
  amount_cents INTEGER NOT NULL,
  reason TEXT,
  FOREIGN KEY(session_id) REFERENCES cash_sessions(id)
);

CREATE TABLE IF NOT EXISTS cash_session_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL UNIQUE,
  totals_json TEXT NOT NULL DEFAULT '{}',
  expected_cash_cents INTEGER NOT NULL DEFAULT 0,
  counted_cash_cents INTEGER NOT NULL DEFAULT 0,
  diff_cash_cents INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(session_id) REFERENCES cash_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_cash_sessions_open ON cash_sessions(status, operator_id, store_id);
CREATE INDEX IF NOT EXISTS idx_orders_cash_status ON orders(cash_session_id, status);
