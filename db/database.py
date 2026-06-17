import os
import shutil
import sqlite3
import sys
import threading
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)

def _user_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "SorveteriaDesktop" / "data"
    return BASE_DIR / "data"

DATA_DIR = _user_data_dir()
DB_PATH = DATA_DIR / "loja.db"

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    SCHEMA_PATH = Path(sys._MEIPASS) / "db" / "schema.sql"
else:
    SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Evita que o app rode sem schema/migrações aplicadas
_initialized = False
_init_lock = threading.Lock()


class _ManagedConnection(sqlite3.Connection):
    """Fecha a conexao automaticamente ao sair do contexto with."""

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def _raw_conn():
    """Conexão direta (sem chamar init_db) para evitar recursão."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        try:
            if not os.access(DB_PATH, os.W_OK):
                os.chmod(DB_PATH, 0o666)
        except Exception:
            logger.exception("Failed to adjust DB permissions for %s", DB_PATH)
    conn = sqlite3.connect(DB_PATH, factory=_ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_conn():
    """
    Retorna uma conexão pronta para uso, garantindo que:
    - schema.sql foi aplicado em banco novo
    - migrações foram executadas
    """
    global _initialized
    if not _initialized:
        with _init_lock:
            if not _initialized:
                _maybe_migrate_legacy_db()
                init_db()
                _initialized = True
    return _raw_conn()


def _catalog_counts(db_path: Path) -> tuple[int, int]:
    """
    Retorna (categorias, produtos) do banco informado.
    Em erro de leitura/schema, devolve (0, 0).
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM categories")
        categories = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM products WHERE COALESCE(active, 1) = 1")
        products = int(cur.fetchone()[0] or 0)
        return categories, products
    except Exception:
        return 0, 0
    finally:
        if conn is not None:
            conn.close()


def _bundled_seed_db_candidates() -> list[Path]:
    """
    Candidatos de banco seed empacotado para primeira copia.
    """
    candidates: list[Path] = []

    # Em modo frozen, costuma resolver para .../_internal
    candidates.append(BASE_DIR / "data" / "loja.db")

    # Em alguns cenarios, _MEIPASS aponta diretamente para o dir interno.
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "data" / "loja.db")

    # Diretório do executavel (instalado em Program Files) com estrutura onedir.
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "data" / "loja.db")
        candidates.append(exe_dir / "data" / "loja.db")
    except Exception:
        logger.exception("Failed to inspect executable directory for seed DB")

    # Remove duplicados preservando ordem.
    unique: list[Path] = []
    seen: set[str] = set()
    for c in candidates:
        key = str(c).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


def _maybe_migrate_legacy_db():
    """
    Em modo frozen:
    - copia banco seed para %LOCALAPPDATA% quando ainda nao existe;
    - se existir banco local vazio (0 categorias e 0 produtos), repoe pelo seed.
    """
    if not getattr(sys, "frozen", False):
        return

    seed = None
    for candidate in _bundled_seed_db_candidates():
        if candidate.exists():
            seed = candidate
            break
    if not seed:
        return

    seed_categories, seed_products = _catalog_counts(seed)
    if seed_categories <= 0 and seed_products <= 0:
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists():
        try:
            shutil.copy2(seed, DB_PATH)
        except Exception:
            logger.exception("Failed to copy seed DB to %s", DB_PATH)
        return

    current_categories, current_products = _catalog_counts(DB_PATH)
    if current_categories == 0 and current_products == 0:
        try:
            backup = DB_PATH.with_suffix(".empty.bak")
            shutil.copy2(DB_PATH, backup)
        except Exception:
            logger.exception("Failed to backup empty DB before restore")
        try:
            shutil.copy2(seed, DB_PATH)
        except Exception:
            logger.exception("Failed to restore seed DB over empty DB")


def migrate_db():
    """
    Migrações seguras (idempotentes):
    - adiciona colunas caso não existam
    - cria tabelas auxiliares com IF NOT EXISTS
    """
    with _raw_conn() as conn:
        # ---------- categories ----------
        cols = conn.execute("PRAGMA table_info(categories)").fetchall()
        col_names = {c["name"] for c in cols}

        if "active" not in col_names:
            conn.execute("ALTER TABLE categories ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        if "image_path" not in col_names:
            conn.execute("ALTER TABLE categories ADD COLUMN image_path TEXT")

        # ---------- products ----------
        cols = conn.execute("PRAGMA table_info(products)").fetchall()
        col_names = {c["name"] for c in cols}

        if "cost_price_cents" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN cost_price_cents INTEGER NOT NULL DEFAULT 0")

        if "freight_cost_cents" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN freight_cost_cents INTEGER NOT NULL DEFAULT 0")

        if "other_cost_cents" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN other_cost_cents INTEGER NOT NULL DEFAULT 0")

        if "tax_percent_bp" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN tax_percent_bp INTEGER NOT NULL DEFAULT 0")

        if "overhead_percent_bp" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN overhead_percent_bp INTEGER NOT NULL DEFAULT 0")

        if "sold_by_kg" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN sold_by_kg INTEGER NOT NULL DEFAULT 0")

        if "barcode" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN barcode TEXT")
        if "track_stock" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN track_stock INTEGER NOT NULL DEFAULT 0")
        if "stock_qty" not in col_names:
            conn.execute("ALTER TABLE products ADD COLUMN stock_qty INTEGER NOT NULL DEFAULT 0")

        # ---------- orders ----------
        cols = conn.execute("PRAGMA table_info(orders)").fetchall()
        col_names = {c["name"] for c in cols}

        if "cash_session_id" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN cash_session_id INTEGER")

        if "canceled_at" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN canceled_at TEXT NULL")
        if "canceled_reason" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN canceled_reason TEXT")
        if "operator_id" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN operator_id INTEGER")
        if "store_id" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN store_id INTEGER")
        if "pdf_path" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN pdf_path TEXT")
        if "whatsapp_sent_at" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN whatsapp_sent_at TEXT")
        if "whatsapp_send_status" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN whatsapp_send_status TEXT")
        if "fiscal_status" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_status TEXT NOT NULL DEFAULT 'PENDING'")
        if "fiscal_doc_type" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_doc_type TEXT")
        if "fiscal_number" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_number TEXT")
        if "fiscal_series" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_series TEXT")
        if "fiscal_access_key" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_access_key TEXT")
        if "fiscal_protocol" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_protocol TEXT")
        if "fiscal_qr_url" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_qr_url TEXT")
        if "fiscal_xml_path" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_xml_path TEXT")
        if "fiscal_emitted_at" not in col_names:
            conn.execute("ALTER TABLE orders ADD COLUMN fiscal_emitted_at TEXT")

        # ---------- payments ----------
        cols = conn.execute("PRAGMA table_info(payments)").fetchall()
        col_names = {c["name"] for c in cols}

        if "change_cents" not in col_names:
            conn.execute("ALTER TABLE payments ADD COLUMN change_cents INTEGER NOT NULL DEFAULT 0")

        # ---------- caixa (tabelas) ----------
        conn.execute("""
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
        )
        """)

        # ---------- cash_sessions (colunas novas) ----------
        cols = conn.execute("PRAGMA table_info(cash_sessions)").fetchall()
        col_names = {c["name"] for c in cols}
        if "operator_id" not in col_names:
            conn.execute("ALTER TABLE cash_sessions ADD COLUMN operator_id INTEGER")
        if "store_id" not in col_names:
            conn.execute("ALTER TABLE cash_sessions ADD COLUMN store_id INTEGER")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS cash_movements (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          type TEXT NOT NULL,
          amount_cents INTEGER NOT NULL,
          reason TEXT,
          FOREIGN KEY(session_id) REFERENCES cash_sessions(id)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS cash_session_summary (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL UNIQUE,
          totals_json TEXT NOT NULL DEFAULT '{}',
          expected_cash_cents INTEGER NOT NULL DEFAULT 0,
          counted_cash_cents INTEGER NOT NULL DEFAULT 0,
          diff_cash_cents INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY(session_id) REFERENCES cash_sessions(id)
        )
        """)

        conn.execute("""
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
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS external_task_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_type TEXT NOT NULL,
          payload_json TEXT NOT NULL DEFAULT '{}',
          attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 5,
          next_run_at TEXT NOT NULL DEFAULT (datetime('now')),
          last_error TEXT,
          status TEXT NOT NULL DEFAULT 'PENDING',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)

        # ---------- loyalty_ledger (FK order_id) ----------
        conn.execute("""
        CREATE TABLE IF NOT EXISTS loyalty_ledger (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER NOT NULL,
          order_id INTEGER NULL,
          delta_points INTEGER NOT NULL,
          reason TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
          FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
        )
        """)

        # ---------- order_items: product_id deve ser nullable (item livre) ----------
        oi_cols = conn.execute("PRAGMA table_info(order_items)").fetchall()
        pid_col = next((c for c in oi_cols if c["name"] == "product_id"), None)
        if pid_col and int(pid_col["notnull"]) == 1:
            conn.execute("""
            CREATE TABLE order_items_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id INTEGER NOT NULL,
              product_id INTEGER NULL,
              variant_id INTEGER NULL,
              qty INTEGER NOT NULL DEFAULT 1,
              unit_price_cents INTEGER NOT NULL DEFAULT 0,
              notes TEXT NOT NULL DEFAULT '',
              FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
              FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
            )
            """)
            conn.execute("""
            INSERT INTO order_items_new (id, order_id, product_id, variant_id, qty, unit_price_cents, notes)
            SELECT id, order_id, product_id, variant_id, qty, unit_price_cents, COALESCE(notes, '')
            FROM order_items
            """)
            conn.execute("DROP TABLE order_items")
            conn.execute("ALTER TABLE order_items_new RENAME TO order_items")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)")

        # ---------- loyalty_ledger (FK order_id) ----------
        fk_list = conn.execute("PRAGMA foreign_key_list(loyalty_ledger)").fetchall()
        has_order_fk = any(fk["from"] == "order_id" and fk["table"] == "orders" for fk in fk_list)
        if not has_order_fk:
            conn.execute("""
            CREATE TABLE loyalty_ledger_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              customer_id INTEGER NOT NULL,
              order_id INTEGER NULL,
              delta_points INTEGER NOT NULL,
              reason TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
              FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
            )
            """)
            conn.execute("""
            INSERT INTO loyalty_ledger_new (id, customer_id, order_id, delta_points, reason, created_at)
            SELECT id, customer_id, order_id, delta_points, reason, created_at
            FROM loyalty_ledger
            """)
            conn.execute("DROP TABLE loyalty_ledger")
            conn.execute("ALTER TABLE loyalty_ledger_new RENAME TO loyalty_ledger")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_loyalty_customer ON loyalty_ledger(customer_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_cash_status ON orders(cash_session_id, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_fiscal_status ON orders(fiscal_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cash_sessions_open ON cash_sessions(status, operator_id, store_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_logs_order ON whatsapp_logs(order_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ext_task_status_next ON external_task_queue(status, next_run_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ext_task_type ON external_task_queue(task_type)")

        conn.commit()


def init_db():
    """
    Roda schema.sql somente no primeiro uso (banco novo).
    Depois sempre roda migrate_db().
    """
    _maybe_migrate_legacy_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    first_run = not DB_PATH.exists()

    with _raw_conn() as conn:
        if first_run:
            schema = SCHEMA_PATH.read_text(encoding="utf-8")
            conn.executescript(schema)
            conn.commit()

    migrate_db()
