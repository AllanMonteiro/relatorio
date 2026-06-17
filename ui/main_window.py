from ui.cash_widget import CashWidget
from ui.import_widget import ImportWidget
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QFrame,
    QMessageBox, QPushButton, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QSpinBox
)
from PySide6.QtGui import QPixmap, QImageReader
from PySide6.QtCore import Qt, QTimer

from ui.pdv_widget import PDVWidget
from ui.kitchen_widget import KitchenWidget
from ui.products_widget import ProductsWidget
from ui.settings_widget import SettingsWidget
from ui.loyalty_widget import LoyaltyWidget

from services.settings_service import (
    load_github_token,
    load_settings,
    get_effective_report_url,
    get_report_local_index_path,
)
from ui.theme import qss_dark, qss_light, qss_blue_grad, qss_green_grad, qss_cream_grad
from services.cash_service import open_session, get_current_session


class OpenCashSessionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Caixa")
        self.setModal(True)
        self.setMinimumWidth(360)

        self._opening_cents = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        layout.addLayout(form)

        self.operator_id = QSpinBox()
        self.operator_id.setRange(1, 10_000_000)
        self.operator_id.setValue(1)
        self.operator_id.setMinimumHeight(34)
        form.addRow("Operator ID:", self.operator_id)

        self.store_id = QSpinBox()
        self.store_id.setRange(1, 10_000_000)
        self.store_id.setValue(1)
        self.store_id.setMinimumHeight(34)
        form.addRow("Store ID:", self.store_id)

        self.opening_edit = QLineEdit("0,00")
        self.opening_edit.setMinimumHeight(34)
        self.opening_edit.setPlaceholderText("Fundo de caixa (R$)")
        form.addRow("Fundo inicial:", self.opening_edit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #b91c1c;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if ok_btn:
            ok_btn.setText("Abrir")
            ok_btn.setObjectName("PrimaryButton")
        if cancel_btn:
            cancel_btn.setText("Cancelar")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.opening_edit.setFocus()
        self.opening_edit.selectAll()

    @staticmethod
    def _cents_from_brl(text: str) -> int:
        t = (text or "").strip().replace(".", "").replace(",", ".")
        if not t:
            return -1
        return int(round(float(t) * 100))

    def _on_accept(self):
        try:
            opening = self._cents_from_brl(self.opening_edit.text())
        except Exception:
            opening = -1
        if opening < 0:
            self.error_label.setText("Valor invalido. Ex: 100,00")
            self.error_label.setVisible(True)
            self.opening_edit.setFocus()
            return
        self._opening_cents = int(opening)
        self.accept()

    def values(self) -> tuple[int, int, int]:
        return int(self.operator_id.value()), int(self.store_id.value()), int(self._opening_cents or 0)



class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()

        self.app = app
        self.settings = load_settings()
        self._startup_fit_done = False

        self.setWindowTitle(self.settings.get("app_name", "NexoGest"))
        self.setMinimumSize(860, 560)
        self.apply_window_size_from_screen()

        container = QWidget()
        container.setObjectName("AppRoot")
        root = QVBoxLayout(container)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        self.header = QFrame()
        self.header.setObjectName("HeaderBar")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(20, 14, 20, 14)
        h.setSpacing(14)

        self.logo = QLabel()
        self.logo.setFixedSize(60, 60)
        self.logo.setAlignment(Qt.AlignCenter)
        h.addWidget(self.logo)

        texts = QVBoxLayout()
        self.lbl_app = QLabel(self.settings.get("app_name", "NexoGest"))
        self.lbl_app.setObjectName("HeaderAppName")
        texts.addWidget(self.lbl_app)

        self.lbl_company = QLabel(self.settings.get("company_name", "Minha Empresa"))
        self.lbl_company.setObjectName("HeaderCompany")
        texts.addWidget(self.lbl_company)

        h.addLayout(texts, 1)

        self.badge = QLabel()
        self.badge.setObjectName("HeaderBadge")
        h.addWidget(self.badge, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.btn_report_link = QPushButton("Copiar link do relat\u00f3rio")
        self.btn_report_link.setObjectName("GhostButton")
        self.btn_report_link.clicked.connect(self.copy_report_url)
        h.addWidget(self.btn_report_link, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self.header)

        tabs = QTabWidget()
        tabs.setObjectName("MainTabs")
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        self.tabs = tabs
        self.pdv_widget = PDVWidget()
        tabs.addTab(self.pdv_widget, "PDV")
        self.cash_widget = CashWidget()
        tabs.addTab(self.cash_widget, "Caixa")
        tabs.addTab(KitchenWidget(), "Cozinha")
        self.products_widget = ProductsWidget(on_categories_changed=self.on_categories_changed)
        tabs.addTab(
            self.products_widget,
            "Produtos"
        )
        self.settings_widget = SettingsWidget(
            on_settings_changed=self.on_settings_changed,
            on_categories_changed=self.on_categories_changed
        )
        tabs.addTab(
            self.settings_widget,
            "Configura\u00e7\u00f5es"
        )
        tabs.addTab(LoyaltyWidget(), "Fidelidade")
        tabs.addTab(ImportWidget(), "Importar")
        root.addWidget(tabs, 1)

        self.setCentralWidget(container)

        self.apply_header_logo()
        self.apply_theme()

        tabs.currentChanged.connect(self.on_tab_changed)
        QTimer.singleShot(0, self.ensure_cash_session)
        QTimer.singleShot(0, self._bind_screen_tracking)

    def apply_window_size_from_screen(self):
        screen = self.app.primaryScreen() or self.screen()
        if not screen:
            self.resize(1300, 760)
            return

        ag = screen.availableGeometry()
        if ag.width() <= 1366 or ag.height() <= 768:
            self.setGeometry(ag.adjusted(2, 2, -2, -2))
            return

        target_w = int(ag.width() * 0.98)
        target_h = int(ag.height() * 0.96)
        target_w = max(960, min(target_w, ag.width()))
        target_h = max(620, min(target_h, ag.height()))
        self.resize(target_w, target_h)

        frame = self.frameGeometry()
        frame.moveCenter(ag.center())
        self.move(frame.topLeft())

    def showEvent(self, event):
        super().showEvent(event)
        if not self._startup_fit_done:
            self._startup_fit_done = True
            QTimer.singleShot(0, self.ensure_window_fit_to_screen)

    def _bind_screen_tracking(self):
        wh = self.windowHandle()
        if not wh:
            return
        try:
            wh.screenChanged.connect(lambda _screen: self.ensure_window_fit_to_screen())
        except Exception:
            pass

    def ensure_window_fit_to_screen(self):
        screen = None
        wh = self.windowHandle()
        if wh:
            screen = wh.screen()
        screen = screen or self.screen() or self.app.primaryScreen()
        if not screen:
            return

        ag = screen.availableGeometry()
        if self.isMaximized() or self.isFullScreen():
            return

        max_w = max(860, ag.width() - 8)
        max_h = max(560, ag.height() - 8)
        target_w = min(max(860, self.width()), max_w)
        target_h = min(max(560, self.height()), max_h)
        self.resize(target_w, target_h)

        frame = self.frameGeometry()
        if (
            frame.left() < ag.left()
            or frame.top() < ag.top()
            or frame.right() > ag.right()
            or frame.bottom() > ag.bottom()
        ):
            frame.moveCenter(ag.center())
            self.move(frame.topLeft())

    def _cents_from_brl(self, text: str) -> int:
        t = (text or "").strip().replace(".", "").replace(",", ".")
        if not t:
            return -1
        return int(round(float(t) * 100))

    def ensure_cash_session(self):
        existing = get_current_session()
        if existing:
            QMessageBox.information(
                self,
                "Caixa",
                f"Caixa j\u00e1 aberto (sess\u00e3o #{int(existing['id'])})."
            )
            return

        dialog = OpenCashSessionDialog(self)
        if dialog.exec() != QDialog.Accepted:
            QMessageBox.warning(self, "Caixa", "Caixa n\u00e3o aberto. Vendas ficar\u00e3o bloqueadas.")
            return
        op_id, store_id, opening = dialog.values()

        try:
            sid = open_session(opening, operator_id=op_id, store_id=store_id)
            QMessageBox.information(self, "Caixa", f"Caixa aberto (sess\u00e3o #{int(sid)}).")
        except ValueError as e:
            QMessageBox.critical(self, "Caixa", str(e))

    def apply_theme(self):
        theme = (self.settings.get("theme") or "blue_grad").lower()
        theme_map = {
            "blue_grad": (qss_blue_grad, "Azul Gradiente"),
            "green_grad": (qss_green_grad, "Verde Gradiente"),
            "cream_grad": (qss_cream_grad, "Creme Gradiente"),
            "dark": (qss_dark, "Escuro"),
            "light": (qss_light, "Claro"),
        }
        qss_fn, label = theme_map.get(theme, theme_map["blue_grad"])
        self.app.setStyleSheet(qss_fn())
        self.badge.setText(f"Tema: {label}")

    def apply_header_logo(self):
        path = (self.settings.get("company_logo_path") or "").strip()
        if path:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            image = reader.read()
            if not image.isNull():
                dpr = max(1.0, float(self.devicePixelRatioF()))
                tw = max(1, int(self.logo.width() * dpr))
                th = max(1, int(self.logo.height() * dpr))
                image = image.scaled(tw, th, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                px = QPixmap.fromImage(image)
                px.setDevicePixelRatio(dpr)
                self.logo.setPixmap(px)
                self.logo.setText("")
                return

        self.logo.setText("N")
        self.logo.setStyleSheet("color: white; font-weight: 900; font-size: 24px;")

    def on_settings_changed(self, new_settings: dict):
        self.settings = new_settings
        self.setWindowTitle(self.settings.get("app_name", "NexoGest"))
        self.lbl_app.setText(self.settings.get("app_name", "NexoGest"))
        self.lbl_company.setText(self.settings.get("company_name", "Minha Empresa"))
        self.apply_header_logo()
        self.apply_theme()

    def on_categories_changed(self):
        if self.pdv_widget:
            self.pdv_widget.build_category_buttons()
        if getattr(self, "settings_widget", None):
            self.settings_widget.load_category_images()
        if getattr(self, "products_widget", None):
            self.products_widget.load_categories()

    def on_tab_changed(self, _idx: int):
        if self.pdv_widget:
            self.pdv_widget.build_category_buttons()
        if self.cash_widget:
            self.cash_widget.refresh()
        if getattr(self, "settings_widget", None):
            self.settings_widget.load_category_images()
        if getattr(self, "products_widget", None):
            self.products_widget.refresh()

    def copy_report_url(self):
        url = get_effective_report_url(self.settings)
        if not url:
            QMessageBox.warning(self, "Relat\u00f3rio", "Link do relat\u00f3rio n\u00e3o configurado.")
            return

        local_index = get_report_local_index_path()
        has_online_publish_token = bool(load_github_token().strip())
        if not has_online_publish_token and local_index.exists():
            self.app.clipboard().setText(str(local_index))
            QMessageBox.information(
                self,
                "Relat\u00f3rio",
                "Esta instala\u00e7\u00e3o ainda n\u00e3o tem publica\u00e7\u00e3o online configurada.\n"
                "Foi copiado o caminho do relat\u00f3rio local.\n\n"
                "Para gerar link web em outra m\u00e1quina, configure o token GitHub e publique o relat\u00f3rio no GitHub Pages.",
            )
            return

        self.app.clipboard().setText(url)
        QMessageBox.information(self, "Relat\u00f3rio", "Link do relat\u00f3rio copiado.")


