PRAGMA foreign_keys = ON;

-- =========================
-- Categorias / Produtos
-- =========================
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,
  image_path TEXT
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NULL,
  name TEXT NOT NULL,
  barcode TEXT,
  active INTEGER NOT NULL DEFAULT 1,

  -- preços em centavos
  cost_price_cents INTEGER NOT NULL DEFAULT 0,      -- custo
  freight_cost_cents INTEGER NOT NULL DEFAULT 0,    -- frete
  other_cost_cents INTEGER NOT NULL DEFAULT 0,      -- outros
  tax_percent_bp INTEGER NOT NULL DEFAULT 0,        -- imposto em basis points (ex: 8,50% = 850)
  overhead_percent_bp INTEGER NOT NULL DEFAULT 0,   -- funcionário/adm em bp
  base_price_cents INTEGER NOT NULL DEFAULT 0,      -- preço de venda (unidade)
  sold_by_kg INTEGER NOT NULL DEFAULT 0,            -- vendido por kg
  track_stock INTEGER NOT NULL DEFAULT 0,
  stock_qty INTEGER NOT NULL DEFAULT 0,

  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(active);


-- =========================
-- Clientes / Fidelidade
-- =========================
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,

  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);

-- =========================
-- Mesas
-- =========================
CREATE TABLE IF NOT EXISTS tables (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  label TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1
);


-- =========================
-- Pedidos / Itens / Pagamentos
-- =========================
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  table_id INTEGER NULL,
  customer_id INTEGER NULL,
  operator_id INTEGER NULL,
  store_id INTEGER NULL,

  status TEXT NOT NULL DEFAULT 'OPEN',
  total_cents INTEGER NOT NULL DEFAULT 0,
  discount_cents INTEGER NOT NULL DEFAULT 0,

  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  closed_at TEXT NULL,
  canceled_at TEXT NULL,
  canceled_reason TEXT NULL,
  pdf_path TEXT NULL,
  whatsapp_sent_at TEXT NULL,
  whatsapp_send_status TEXT NULL,
  fiscal_status TEXT NOT NULL DEFAULT 'PENDING',
  fiscal_doc_type TEXT NULL,
  fiscal_number TEXT NULL,
  fiscal_series TEXT NULL,
  fiscal_access_key TEXT NULL,
  fiscal_protocol TEXT NULL,
  fiscal_qr_url TEXT NULL,
  fiscal_xml_path TEXT NULL,
  fiscal_emitted_at TEXT NULL,
  cash_session_id INTEGER,

  FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE SET NULL,
  FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
);

-- WhatsApp logs
CREATE TABLE IF NOT EXISTS whatsapp_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NULL,
  provider TEXT NOT NULL,
  to_phone TEXT NOT NULL,
  file_path TEXT,
  caption TEXT,
  success INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  response_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_logs_order ON whatsapp_logs(order_id);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_fiscal_status ON orders(fiscal_status);
CREATE INDEX IF NOT EXISTS idx_orders_table ON orders(table_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_cash_session ON orders(cash_session_id);

-- Pontos de fidelidade (ledger)
CREATE TABLE IF NOT EXISTS loyalty_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL,
  order_id INTEGER NULL,
  delta_points INTEGER NOT NULL, -- +ganha / -resgata
  reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_loyalty_customer ON loyalty_ledger(customer_id);


CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL,

  product_id INTEGER NULL,      -- pode ser NULL para item livre
  variant_id INTEGER NULL,      -- reservado p/ futuro

  qty INTEGER NOT NULL DEFAULT 1,
  unit_price_cents INTEGER NOT NULL DEFAULT 0,

  notes TEXT NOT NULL DEFAULT '',

  created_at TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);


CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL,

  method TEXT NOT NULL,              -- CASH / PIX / CARD / CARD_DEBIT / CARD_CREDIT
  amount_cents INTEGER NOT NULL DEFAULT 0,
  change_cents INTEGER NOT NULL DEFAULT 0,

  created_at TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);


-- =========================
-- CAIXA (SESSÕES DIÁRIAS)
-- =========================
CREATE TABLE IF NOT EXISTS cash_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opened_at TEXT NOT NULL DEFAULT (datetime('now')),
  closed_at TEXT,
  opening_cash_cents INTEGER NOT NULL DEFAULT 0,  -- fundo de troco
  closing_cash_cents INTEGER NOT NULL DEFAULT 0,  -- contado no fechamento
  status TEXT NOT NULL DEFAULT 'OPEN',            -- OPEN/CLOSED
  notes TEXT
);

-- Movimentações manuais do caixa (entrada/saída)
CREATE TABLE IF NOT EXISTS cash_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  type TEXT NOT NULL,               -- IN / OUT
  amount_cents INTEGER NOT NULL,
  reason TEXT,
  FOREIGN KEY(session_id) REFERENCES cash_sessions(id)
);

-- =========================
-- Ajuste final: agora que orders existe, recria loyalty_ledger com FK opcional
-- (o mais simples: manter sem FK de order_id, para não quebrar migração)
-- =========================
