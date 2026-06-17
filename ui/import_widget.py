from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont


class _ImportWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        try:
            from services.import_service import import_from_excel
            self.finished.emit(import_from_excel(self._path))
        except Exception as e:
            self.error.emit(str(e))


class ImportWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = ""
        self._parsed_records: list[dict] = []
        self._worker: _ImportWorker | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # Title
        lbl_title = QLabel("Importar Vendas Retroativas")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        lbl_title.setFont(font)
        root.addWidget(lbl_title)

        # Description
        lbl_desc = QLabel(
            "Use esta tela para registrar vendas de períodos em que o sistema estava indisponível.\n"
            "Baixe o modelo Excel, preencha com os dados das vendas e importe o arquivo."
        )
        lbl_desc.setWordWrap(True)
        root.addWidget(lbl_desc)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        # File row
        file_row = QHBoxLayout()

        self.lbl_file = QLabel("Nenhum arquivo selecionado")
        self.lbl_file.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        file_row.addWidget(self.lbl_file, 1)

        self.btn_template = QPushButton("Baixar Modelo Excel")
        self.btn_template.setToolTip("Gera uma planilha de exemplo com o formato esperado")
        self.btn_template.clicked.connect(self._download_template)
        file_row.addWidget(self.btn_template)

        self.btn_browse = QPushButton("Selecionar Arquivo (.xlsx)")
        self.btn_browse.setObjectName("PrimaryButton")
        self.btn_browse.clicked.connect(self._browse_file)
        file_row.addWidget(self.btn_browse)

        root.addLayout(file_row)

        # Preview label
        self.lbl_preview = QLabel("Nenhum arquivo carregado")
        root.addWidget(self.lbl_preview)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Data", "Hora", "Pedido", "Descrição", "Qtd", "Preço Unit.", "Pagamento"]
        )
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for col in (0, 1, 2, 4, 5, 6):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)
        root.addWidget(self.table, 1)

        # Import row
        import_row = QHBoxLayout()
        import_row.addStretch()

        self.btn_import = QPushButton("Importar para o Sistema →")
        self.btn_import.setObjectName("PrimaryButton")
        self.btn_import.setMinimumHeight(36)
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._import)
        import_row.addWidget(self.btn_import)

        root.addLayout(import_row)

        # Result label
        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        root.addWidget(self.lbl_result)

    # ------------------------------------------------------------------
    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Planilha de Vendas", "", "Excel (*.xlsx *.xls)"
        )
        if not path:
            return
        self._file_path = path
        self.lbl_file.setText(Path(path).name)
        self.lbl_result.setText("")
        self._parse_preview()

    def _parse_preview(self):
        try:
            from services.import_service import parse_excel
            records, warnings = parse_excel(self._file_path)
            self._parsed_records = records

            self.table.setRowCount(len(records))
            for ri, rec in enumerate(records):
                preco = f"R$ {rec['preco_unitario'] / 100:.2f}".replace(".", ",")
                self.table.setItem(ri, 0, QTableWidgetItem(rec["data"]))
                self.table.setItem(ri, 1, QTableWidgetItem(rec["hora"]))
                self.table.setItem(ri, 2, QTableWidgetItem(rec["pedido_key"]))
                self.table.setItem(ri, 3, QTableWidgetItem(rec["descricao"]))
                self.table.setItem(ri, 4, QTableWidgetItem(str(rec["quantidade"])))
                self.table.setItem(ri, 5, QTableWidgetItem(preco))
                self.table.setItem(ri, 6, QTableWidgetItem(rec["pagamento"]))

            self.lbl_preview.setText(f"Pré-visualização: {len(records)} item(ns) encontrado(s)")

            msg_parts = []
            if warnings:
                msg_parts.append("Avisos:\n" + "\n".join(warnings[:8]))
                if len(warnings) > 8:
                    msg_parts.append(f"... e mais {len(warnings) - 8} aviso(s).")
            self.lbl_result.setText("\n".join(msg_parts))

            self.btn_import.setEnabled(len(records) > 0)
        except Exception as e:
            self.lbl_result.setText(f"Erro ao ler o arquivo: {e}")
            self.btn_import.setEnabled(False)

    def _download_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Modelo Excel", "modelo_importacao_vendas.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            from services.import_service import generate_template_excel
            generate_template_excel(path)
            QMessageBox.information(
                self,
                "Modelo Gerado",
                f"Modelo salvo em:\n{path}\n\n"
                "Abra o arquivo, preencha com os dados das vendas\n"
                "e depois use 'Selecionar Arquivo' para importar.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível gerar o modelo:\n{e}")

    def _import(self):
        if not self._parsed_records:
            QMessageBox.warning(self, "Importar", "Nenhum dado carregado para importar.")
            return

        # Count orders (grouped)
        from services.import_service import _group_orders
        orders = _group_orders(self._parsed_records)

        reply = QMessageBox.question(
            self,
            "Confirmar Importação",
            f"Serão criadas {len(orders)} venda(s) com {len(self._parsed_records)} item(ns).\n\n"
            "As vendas serão registradas como fechadas nas datas da planilha.\n"
            "⚠ Não importe o mesmo arquivo mais de uma vez.\n\n"
            "Deseja continuar?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.btn_import.setEnabled(False)
        self.btn_browse.setEnabled(False)
        self.btn_template.setEnabled(False)
        self.lbl_result.setText("Importando, aguarde...")

        self._worker = _ImportWorker(self._file_path, self)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, result: dict):
        self.btn_browse.setEnabled(True)
        self.btn_template.setEnabled(True)

        imported = result.get("imported_orders", 0)
        errors = result.get("errors", [])
        warnings = result.get("warnings", [])

        msg = f"Importação concluída!\n{imported} venda(s) registrada(s) no sistema."
        if errors:
            msg += "\n\nErros:\n" + "\n".join(errors[:10])
        if warnings:
            msg += "\n\nAvisos:\n" + "\n".join(warnings[:5])

        self.lbl_result.setText(msg)

        if errors:
            QMessageBox.warning(self, "Importação com Erros", msg)
        else:
            QMessageBox.information(self, "Importação Concluída", msg)

    def _on_error(self, error: str):
        self.btn_import.setEnabled(True)
        self.btn_browse.setEnabled(True)
        self.btn_template.setEnabled(True)
        self.lbl_result.setText(f"Erro: {error}")
        QMessageBox.critical(self, "Erro na Importação", error)
