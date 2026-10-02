from __future__ import annotations

import csv
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import subprocess
import time
import re

from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QPalette, QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QSplitter,
    QSizePolicy,
)
from dotenv import load_dotenv


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")

from .run_pipeline import (
    build_exports,
    publish_to_dropbox,
)

from .upscale import upscale_image

from .mockups import (
    build_all_mockups_for_product,
    build_final_etsy_set_for_product,
)

from .delivery_pdf import make_delivery_pdf

from .dropbox_ops import normalize_share_link


# ---------- Paths ----------
def repo_root() -> Path:
    return REPO_ROOT


QUEUE_CSV = Path(os.getenv("RR_QUEUE_CSV", repo_root() / "data" / "products_queue.csv")).expanduser().resolve()
PRODUCTS_DIR = Path(os.getenv("RR_PRODUCTS_DIR", repo_root() / "products")).expanduser().resolve()


# ---------- Data ----------
STATUSES = ["NEW", "HAS_MASTER", "APPROVED", "REJECTED", "BUILT", "READY", "PUBLISHED"]


@dataclass
class Row:
    product_id: str
    title: str
    status: str
    notes: str
    master_path: str
    extras: dict = field(default_factory=dict)  # <- any extra CSV columns preserved


def read_queue(csv_path: Path) -> list[Row]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing queue CSV: {csv_path}")

    rows: list[Row] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            core = {
                "product_id": (r.get("product_id") or "").strip(),
                "title": (r.get("title") or "").strip(),
                "status": (r.get("status") or "NEW").strip(),
                "notes": (r.get("notes") or "").strip(),
                "master_path": (r.get("master_path") or "").strip(),
            }

            extras = {k: (v or "").strip() for k, v in r.items() if k not in core}

            rows.append(
                Row(
                    product_id=core["product_id"],
                    title=core["title"],
                    status=core["status"],
                    notes=core["notes"],
                    master_path=core["master_path"],
                    extras=extras,
                )
            )
    return rows


def write_queue(csv_path: Path, rows: list[Row]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    core_fields = ["product_id", "title", "status", "notes", "master_path"]

    # Collect all extra fieldnames seen across rows (stable sorted order)
    extra_fields = sorted({k for r in rows for k in (r.extras or {}).keys()})

    fieldnames = core_fields + extra_fields

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            rowdict = {
                "product_id": r.product_id,
                "title": r.title,
                "status": r.status,
                "notes": r.notes,
                "master_path": r.master_path,
            }
            for k in extra_fields:
                rowdict[k] = (r.extras or {}).get(k, "")
            writer.writerow(rowdict)

def product_master_dest(product_id: str) -> Path:
    # products/<product_id>/master/raw.png
    return PRODUCTS_DIR / product_id / "master" / "raw.png"

def product_upscaled_path(product_id: str) -> Path:
    return PRODUCTS_DIR / product_id / "master" / "upscaled.png"

def ensure_readme_in_exports(product_id: str) -> Path:
    """
    Ensures README-HowToPrint.pdf exists inside:
      products/<product_id>/exports/README-HowToPrint.pdf
    Source assumed at repo root:
      README-HowToPrint.pdf
    """
    src = repo_root() / "assets" / "README-HowToPrint.pdf"
    if not src.exists():
        raise FileNotFoundError(f"Missing README PDF at repo root: {src}")

    exports_dir = PRODUCTS_DIR / product_id / "exports"
    if not exports_dir.exists():
        raise FileNotFoundError(f"Missing exports folder: {exports_dir}")

    dst = exports_dir / "README-HowToPrint.pdf"
    shutil.copy2(src, dst)
    return dst

class TaskWorker(QObject):
    progress = Signal(int, str)   # percent, message
    done = Signal(bool, str)      # success, message

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.fn(self.progress.emit, *self.args, **self.kwargs)
            self.done.emit(True, "Task completed.")
        except Exception as e:
            self.done.emit(False, f"{type(e).__name__}: {e}")

def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()

    palette.setColor(QPalette.Window, QColor(28, 28, 28))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(20, 20, 20))
    palette.setColor(QPalette.AlternateBase, QColor(36, 36, 36))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Highlight, QColor(90, 130, 255))
    palette.setColor(QPalette.HighlightedText, Qt.black)

    app.setPalette(palette)

    app.setStyleSheet("""
        QMainWindow { background: #1c1c1c; }
        QLabel { font-size: 12px; }
        QLineEdit, QTextEdit, QComboBox {
            background: #141414;
            border: 1px solid #3a3a3a;
            border-radius: 8px;
            padding: 8px;
        }
        QTableWidget {
            background: #141414;
            border: 1px solid #3a3a3a;
            gridline-color: #2a2a2a;
            border-radius: 8px;
        }
        QHeaderView::section {
            background: #2a2a2a;
            padding: 8px;
            border: none;
            font-weight: 600;
        }
        QPushButton {
            background: #2d2d2d;
            border: 1px solid #3a3a3a;
            border-radius: 10px;
            padding: 10px 12px;
        }
        QPushButton:hover { background: #353535; }
        QPushButton:disabled { background: #1f1f1f; color: #777; border-color: #2a2a2a; }
        QProgressBar {
            border: 1px solid #3a3a3a;
            border-radius: 8px;
            background: #141414;
            height: 18px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: #5a82ff;
            border-radius: 8px;
        }
    """)

# ---------- GUI ----------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Render & Rise Factory GUI")

        self.rows: list[Row] = []

        self.thread: QThread | None = None
        self.worker: TaskWorker | None = None
        self._last_progress_pct = -1

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["product_id", "title", "status", "notes", "master_path"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_select)

        # Detail fields
        self.pid = QLineEdit()
        self.title = QLineEdit()
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        self.notes = QTextEdit()
        self.master_path = QLineEdit()
        self.thumb = QLabel("No image selected")
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setMinimumHeight(220)
        self.thumb.setStyleSheet("border: 1px solid #3a3a3a; border-radius: 10px; background: #141414;")
        self.thumb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.master_path.setReadOnly(True)

        # Buttons
        self.btn_reload = QPushButton("Reload CSV")
        self.btn_save = QPushButton("Save Changes")
        self.btn_new = QPushButton("Add New Row")

        self.btn_pick_master = QPushButton("Attach Master Image")
        self.btn_open_product = QPushButton("Open Product Folder")
        self.btn_approve = QPushButton("Approve (QA 1)")
        self.btn_reject = QPushButton("Reject (QA 1)")
        self.btn_build = QPushButton("Build Exports")

        self.btn_mockups_all = QPushButton("Generate ALL Mockups")
        self.btn_mockups_final = QPushButton("Generate FINAL Mockups")
        self.btn_open_mockups = QPushButton("Open Mockups Folder")

        self.btn_publish = QPushButton("Publish Dropbox")

        self.btn_delivery_pdf = QPushButton("Prepare Delivery PDF")

        self.btn_reload.clicked.connect(self.load_csv)
        self.btn_save.clicked.connect(self.save_current_row)
        self.btn_new.clicked.connect(self.add_new_row)

        self.btn_pick_master.clicked.connect(self.attach_master)
        self.btn_open_product.clicked.connect(self.open_product_folder)
        self.btn_approve.clicked.connect(lambda: self.set_status_selected("APPROVED"))
        self.btn_reject.clicked.connect(lambda: self.set_status_selected("REJECTED"))
        self.btn_build.clicked.connect(self.build_selected)

        self.btn_mockups_all.clicked.connect(self.generate_mockups_all)
        self.btn_mockups_final.clicked.connect(self.generate_mockups_final)
        self.btn_open_mockups.clicked.connect(self.open_mockups_folder)

        self.btn_publish.clicked.connect(self.publish_selected)

        self.btn_delivery_pdf.clicked.connect(self.prepare_delivery_pdf_selected)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFormat("Idle")

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Logs will appear here...")

        # Layout
        left = QVBoxLayout()
        left.addWidget(QLabel("Queue"))
        left.addWidget(self.table)

        top_btns = QHBoxLayout()
        top_btns.addWidget(self.btn_reload)
        top_btns.addWidget(self.btn_new)
        top_btns.addWidget(self.btn_save)
        left.addLayout(top_btns)

        right = QVBoxLayout()
        right.addWidget(QLabel("Selected Product"))

        right.addWidget(QLabel("product_id"))
        right.addWidget(self.pid)

        right.addWidget(QLabel("title"))
        right.addWidget(self.title)

        right.addWidget(QLabel("status"))
        right.addWidget(self.status)

        right.addWidget(QLabel("notes"))
        right.addWidget(self.notes)

        right.addWidget(QLabel("master_path"))
        right.addWidget(self.master_path)

        right.addWidget(QLabel("Master Preview"))
        right.addWidget(self.thumb)

        action_row1 = QHBoxLayout()
        action_row1.addWidget(self.btn_pick_master)
        action_row1.addWidget(self.btn_open_product)
        right.addLayout(action_row1)

        action_row2 = QHBoxLayout()
        action_row2.addWidget(self.btn_approve)
        action_row2.addWidget(self.btn_reject)
        action_row2.addWidget(self.btn_build)
        right.addLayout(action_row2)

        action_row3 = QHBoxLayout()
        action_row3.addWidget(self.btn_mockups_all)
        action_row3.addWidget(self.btn_mockups_final)
        action_row3.addWidget(self.btn_open_mockups)
        right.addLayout(action_row3)

        action_row4 = QHBoxLayout()
        action_row4.addWidget(self.btn_publish)
        action_row4.addWidget(self.btn_delivery_pdf)
        right.addLayout(action_row4)

        split = QSplitter()
        left_w = QWidget()
        left_w.setLayout(left)

        right_w = QWidget()
        right_v = QVBoxLayout(right_w)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.addLayout(right)

        # Add progress + logs under the right panel
        right_v.addWidget(QLabel("Progress"))
        right_v.addWidget(self.progress)
        right_v.addWidget(QLabel("Logs"))
        right_v.addWidget(self.log)

        split.addWidget(left_w)
        split.addWidget(right_w)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        container = QWidget()
        root_layout = QVBoxLayout(container)
        root_layout.addWidget(split)
        self.setCentralWidget(container)

        self.load_csv()

    # ---------- Helpers ----------
    def error(self, msg: str) -> None:
        QMessageBox.critical(self, "Error", msg)

    def info(self, msg: str) -> None:
        QMessageBox.information(self, "Info", msg)

    def current_index(self) -> int:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return -1
        return sel[0].row()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-scale thumbnail on window resize
        self.update_thumbnail(self.master_path.text().strip())

    # ---------- CSV actions ----------
    def load_csv(self) -> None:
        try:
            self.rows = read_queue(QUEUE_CSV)
        except Exception as e:
            self.error(str(e))
            self.rows = []

        self.table.setRowCount(0)
        for r in self.rows:
            self._add_table_row(r)

        if self.rows:
            self.table.selectRow(0)

    def _add_table_row(self, r: Row) -> None:
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)

        def put(col: int, text: str) -> None:
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, col, item)

        put(0, r.product_id)
        put(1, r.title)
        put(2, r.status)
        put(3, r.notes)
        put(4, r.master_path)

    def save_current_row(self) -> None:
        idx = self.current_index()
        if idx < 0:
            self.error("Select a row first.")
            return

        old_extras = self.rows[idx].extras if idx < len(self.rows) else {}
        self.rows[idx] = Row(
            product_id=self.pid.text().strip(),
            title=self.title.text().strip(),
            status=self.status.currentText().strip(),
            notes=self.notes.toPlainText().strip(),
            master_path=self.master_path.text().strip(),
            extras=old_extras,  # preserve unknown columns
        )

        try:
            write_queue(QUEUE_CSV, self.rows)
        except Exception as e:
            self.error(str(e))
            return

        # refresh table row
        self.table.item(idx, 0).setText(self.rows[idx].product_id)
        self.table.item(idx, 1).setText(self.rows[idx].title)
        self.table.item(idx, 2).setText(self.rows[idx].status)
        self.table.item(idx, 3).setText(self.rows[idx].notes)
        self.table.item(idx, 4).setText(self.rows[idx].master_path)

        self.info("Saved.")

    def add_new_row(self) -> None:
        self.rows.append(Row(product_id="", title="", status="NEW", notes="", master_path="", extras={}))
        write_queue(QUEUE_CSV, self.rows)
        self.load_csv()
        self.table.selectRow(len(self.rows) - 1)

    # ---------- Selection ----------
    def on_select(self) -> None:
        idx = self.current_index()
        if idx < 0:
            return
        r = self.rows[idx]
        self.pid.setText(r.product_id)
        self.title.setText(r.title)
        if r.status in STATUSES:
            self.status.setCurrentText(r.status)
        else:
            self.status.setCurrentText("NEW")
        self.notes.setPlainText(r.notes)
        self.master_path.setText(r.master_path)
        self.update_thumbnail(r.master_path)

    # ---------- Product actions ----------
    def attach_master(self) -> None:
        idx = self.current_index()
        if idx < 0:
            self.error("Select a row first.")
            return

        product_id = self.pid.text().strip()
        if not product_id:
            self.error("product_id is required.")
            return

        src, _ = QFileDialog.getOpenFileName(
            self,
            "Select master image",
            str(repo_root()),
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if not src:
            return

        dest = product_master_dest(product_id)
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(src, dest)
        except Exception as e:
            self.error(f"Failed to copy master image:\n{e}")
            return

        # update row fields
        self.master_path.setText(str(dest))
        self.update_thumbnail(str(dest))
        if self.status.currentText() == "NEW":
            self.status.setCurrentText("HAS_MASTER")

        self.save_current_row()

    def open_product_folder(self) -> None:
        product_id = self.pid.text().strip()
        if not product_id:
            self.error("product_id is required.")
            return
        pdir = PRODUCTS_DIR / product_id
        pdir.mkdir(parents=True, exist_ok=True)

        # Windows explorer open
        try:
            import subprocess

            subprocess.Popen(["explorer", str(pdir)])
        except Exception as e:
            self.error(str(e))

    def set_status_selected(self, new_status: str) -> None:
        if new_status not in STATUSES:
            self.error(f"Invalid status: {new_status}")
            return
        self.status.setCurrentText(new_status)
        self.save_current_row()

    def _start_task(self, task_fn, *args):
        # Prevent double-start
        if self.thread is not None:
            self.error("A task is already running.")
            return

        self.set_busy(True)
        self.progress.setValue(0)
        self.progress.setFormat("Working...")
        self._last_progress_pct = -1

        self.thread = QThread()
        self.worker = TaskWorker(task_fn, *args)
        self.worker.moveToThread(self.thread)

        # Always queued => runs on GUI thread
        self.worker.progress.connect(self._on_worker_progress, Qt.QueuedConnection)
        self.worker.done.connect(self._on_worker_done, Qt.QueuedConnection)

        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self._cleanup_worker, Qt.QueuedConnection)

        self.thread.start()

    def _on_worker_progress(self, pct: int, msg: str) -> None:

        if pct < 0:
            # Indeterminate / busy mode
            self.progress.setRange(0, 0)
            self.progress.setFormat("Working...")
            self.log_line(msg)
            return
        else:
            # Back to normal determinate mode
            if self.progress.minimum() == 0 and self.progress.maximum() == 0:
                self.progress.setRange(0, 100)

        # Drop spammy duplicates to reduce repaint pressure
        pct = max(0, min(100, int(pct)))
        if pct == self._last_progress_pct and len(msg) < 3:
            return
        self._last_progress_pct = pct

        self.progress.setValue(pct)
        self.progress.setFormat(f"{pct}%")
        self.log_line(msg)

    def _on_worker_done(self, success: bool, msg: str) -> None:
        # IMPORTANT: Do NOT wait() here. Just request the thread to quit.
        # Cleanup will happen in _cleanup_worker via thread.finished.
        if not success:
            self.log_line(f"ERROR: {msg}")
        else:
            self.log_line("Task finished successfully.")

        if self.thread is not None:
            self.thread.quit()

        # Store final status so cleanup can apply it safely on GUI thread
        self._task_success = success
        self._task_message = msg

    def _cleanup_worker(self) -> None:
        # Runs on GUI thread after thread stops
        success = getattr(self, "_task_success", False)
        msg = getattr(self, "_task_message", "")

        try:
            if self.worker is not None:
                self.worker.deleteLater()
            if self.thread is not None:
                self.thread.deleteLater()
        finally:
            self.worker = None
            self.thread = None
            self.set_busy(False)

        if success:
            # Optional per-task status update
            new_status = getattr(self, "_task_set_status", None)
            if new_status and new_status in STATUSES:
                self.status.setCurrentText(new_status)
                self.save_current_row()

            self.info(msg if msg else "Done.")
        else:
            self.error(msg if msg else "Task failed.")

        self._task_set_status = None

        # Persist last known Dropbox outputs to extras if present
        idx = self.current_index()
        if idx >= 0 and idx < len(self.rows):
            self.rows[idx].extras["dropbox_share_link"] = getattr(self, "_last_share_link", "")
            self.rows[idx].extras["delivery_pdf_path"] = getattr(self, "_last_delivery_pdf", "")
            write_queue(QUEUE_CSV, self.rows)

    def _pretty_title(self) -> str:
        """
        Makes a clean human title for the delivery PDF.
        Priority:
          1) CSV extra field 'display_title' (if you ever add it)
          2) GUI title field (if you typed something human)
          3) Derive from product_id slug
        """
        # 1) extras.display_title if present
        idx = self.current_index()
        if idx >= 0 and idx < len(self.rows):
            dt = (self.rows[idx].extras or {}).get("display_title", "").strip()
            if dt:
                return dt

        # 2) GUI title if it isn't RR-coded
        t = (self.title.text() or "").strip()
        if t and not re.match(r"^RR-\d{4}[_\-\s]", t, flags=re.IGNORECASE):
            return t

        # 3) derive from product_id: RR-0003_koala-organizing..._study-corner
        pid = (self.pid.text() or "").strip()
        pid = re.sub(r"^RR-\d{4}[_\-\s]*", "", pid, flags=re.IGNORECASE)
        pid = pid.replace("_", " ").replace("-", " ").strip()
        pid = re.sub(r"\s+", " ", pid)

        # Title Case but keep small words reasonable
        words = pid.split(" ")
        small = {"a", "an", "the", "and", "or", "of", "in", "on", "with", "to"}
        out = []
        for i, w in enumerate(words):
            lw = w.lower()
            if i != 0 and lw in small:
                out.append(lw)
            else:
                out.append(lw.capitalize())
        return " ".join(out) if out else "Your Download"


    def build_selected(self) -> None:
        idx = self.current_index()
        if idx < 0:
            self.error("Select a row first.")
            return

        product_id = self.pid.text().strip()
        title = self.title.text().strip() or product_id
        master_path_txt = self.master_path.text().strip()

        if not product_id:
            self.error("product_id is required.")
            return
        if not master_path_txt:
            self.error("Attach a master image first.")
            return

        raw_path = Path(master_path_txt)
        if not raw_path.exists():
            self.error(f"Master image not found:\n{raw_path}")
            return

        if self.status.currentText() != "APPROVED":
            self.error("Approve the master image before building exports.")
            return

        upscaled_path = product_upscaled_path(product_id)

        def task(emit, product_id: str, title: str, raw_path: Path, upscaled_path: Path):
            emit(1, "Starting upscale (Upscayl)...")
            emit(2, f"Raw: {raw_path}")
            emit(2, f"Out: {upscaled_path}")

            emit(-1, "Upscaling (Upscayl)...")

            upscale_image(
                raw_path,
                upscaled_path,
                scale=4,
                model="ultrasharp-4x",
                tile_size=256,
            )

            emit(70, "Upscale complete. Building exports...")
            build_exports(product_id, title, upscaled_path)
            emit(100, "Exports complete.")

        # Start safely
        self._task_set_status = "BUILT"
        self._start_task(
            task,
            product_id,
            title,
            raw_path,
            upscaled_path,
        )

        # Set status after task finishes, safely in GUI thread via message box text
        # We'll set it in _cleanup_worker by using the success message
        self._task_message = f"Build complete.\nUpscaled:\n{upscaled_path}\n\nExports created."
        # status update is better done after success:
        # we'll do it in _cleanup_worker using current fields
        self._task_success = False  # will be set by worker

    def open_mockups_folder(self) -> None:
        product_id = self.pid.text().strip()
        if not product_id:
            self.error("product_id is required.")
            return

        mdir = PRODUCTS_DIR / product_id / "mockups" / "etsy"
        mdir.mkdir(parents=True, exist_ok=True)

        try:
            import subprocess
            subprocess.Popen(["explorer", str(mdir)])
        except Exception as e:
            self.error(str(e))

    def generate_mockups_all(self) -> None:
        idx = self.current_index()
        if idx < 0:
            self.error("Select a row first.")
            return

        product_id = self.pid.text().strip()
        if not product_id:
            self.error("product_id is required.")
            return

        # Require exports exist (since mockups insert the 2x3 export)
        exports_dir = PRODUCTS_DIR / product_id / "exports" / "2x3"
        if not exports_dir.exists():
            self.error("Exports not found. Run 'Build Exports' first.")
            return

        product_dir = PRODUCTS_DIR / product_id
        templates_dir = repo_root() / "assets" / "mockup_templates"

        try:
            outs = build_all_mockups_for_product(product_dir, templates_dir)
        except Exception as e:
            self.error(f"Mockups (ALL) failed:\n{e}")
            return

        self.info(f"Generated {len(outs)} mockups in:\n{product_dir / 'mockups/etsy/all'}")

    def generate_mockups_final(self) -> None:
        idx = self.current_index()
        if idx < 0:
            self.error("Select a row first.")
            return

        product_id = self.pid.text().strip()
        if not product_id:
            self.error("product_id is required.")
            return

        exports_dir = PRODUCTS_DIR / product_id / "exports" / "2x3"
        if not exports_dir.exists():
            self.error("Exports not found. Run 'Build Exports' first.")
            return

        product_dir = PRODUCTS_DIR / product_id
        templates_dir = repo_root() / "assets" / "mockup_templates"

        try:
            outs = build_final_etsy_set_for_product(product_dir, templates_dir, seed=1337)
        except Exception as e:
            self.error(f"Mockups (FINAL) failed:\n{e}")
            return

        # Optional: bump status to READY after FINAL set
        self.status.setCurrentText("READY")
        self.save_current_row()

        self.info(f"Generated FINAL set ({len(outs)} files) in:\n{product_dir / 'mockups/etsy'}")

    def update_thumbnail(self, img_path_str: str) -> None:
        p = Path(img_path_str) if img_path_str else None
        if not p or not p.exists():
            self.thumb.setText("No image selected")
            self.thumb.setPixmap(QPixmap())
            return

        pix = QPixmap(str(p))
        if pix.isNull():
            self.thumb.setText("Preview failed")
            self.thumb.setPixmap(QPixmap())
            return

        # Fit to label size while keeping aspect ratio
        w = max(200, self.thumb.width() - 20)
        h = max(200, self.thumb.height() - 20)
        scaled = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb.setPixmap(scaled)
        self.thumb.setText("")

    def log_line(self, msg: str) -> None:
        self.log.append(msg)
        self.log.ensureCursorVisible()

    def set_busy(self, busy: bool) -> None:
        # Disable actions while a task runs
        for b in [
            self.btn_pick_master,
            self.btn_open_product,
            self.btn_approve,
            self.btn_reject,
            self.btn_build,
            getattr(self, "btn_mockups_all", None),
            getattr(self, "btn_mockups_final", None),
            getattr(self, "btn_open_mockups", None),
            self.btn_new,
            self.btn_save,
            self.btn_reload,
        ]:
            if b is not None:
                b.setDisabled(busy)

        if not busy:
            self.progress.setFormat("Idle")
            self.progress.setValue(0)

    def publish_selected(self) -> None:
        idx = self.current_index()
        if idx < 0:
            self.error("Select a row first.")
            return

        product_id = self.pid.text().strip()
        title = self.title.text().strip() or product_id
        if not product_id:
            self.error("product_id is required.")
            return

        exports_dir = PRODUCTS_DIR / product_id / "exports"
        if not exports_dir.exists():
            self.error("Exports not found. Run 'Build Exports' first.")
            return

        def task(emit, product_id: str, title: str):
            emit(-1, "Ensuring README is inside exports...")
            readme_path = ensure_readme_in_exports(product_id)
            emit(10, f"README ready: {readme_path.name}")

            emit(-1, "Uploading exports to Dropbox (clean folder)...")
            _, share_link = publish_to_dropbox(product_id, title)
            emit(100, "Dropbox upload complete.")

            # Store for CSV extras display later if you want
            self._last_share_link = share_link

            share_link = normalize_share_link(share_link, dl=False)  # ensure view-style link

        self._task_set_status = "PUBLISHED"
        self._start_task(task, product_id, title)
        self._task_message = "Dropbox upload complete.\n\nYour customer folder contains:\n- 6 aspect ratio folders\n- README-HowToPrint.pdf"
        self._task_success = False

    def prepare_delivery_pdf_selected(self) -> None:
        idx = self.current_index()
        if idx < 0:
            self.error("Select a row first.")
            return

        product_id = self.pid.text().strip()
        if not product_id:
            self.error("product_id is required.")
            return

        # Require Dropbox link (publish first)
        dropbox_link = ""
        if idx >= 0 and idx < len(self.rows):
            dropbox_link = (self.rows[idx].extras or {}).get("dropbox_link", "").strip()

        if not dropbox_link:
            self.error("No Dropbox link found for this product. Click 'Publish to Dropbox' first.")
            return

        nice_title = self._pretty_title()
        dropbox_link = normalize_share_link(dropbox_link, dl=False)

        def task(emit, product_id: str, nice_title: str, dropbox_link: str):
            emit(-1, "Generating delivery PDF (local only)...")
            pdf_path = make_delivery_pdf(product=product_id, title=nice_title, share_link=dropbox_link)
            self._last_delivery_pdf = str(pdf_path)
            emit(100, f"Delivery PDF created: {pdf_path.name}")

            # store path
            return str(pdf_path)

        result = {"pdf": ""}

        def wrapped_task(emit, product_id: str, nice_title: str, dropbox_link: str):
            result["pdf"] = task(emit, product_id, nice_title, dropbox_link)

        self._start_task(wrapped_task, product_id, nice_title, dropbox_link)
        self._task_message = f"Delivery PDF created:\n{result['pdf']}"
        self._task_success = False

        # Persist delivery path into CSV extras after done (best-effort)
        self._task_set_status = None  # don't change status just for creating pdf

def main() -> None:
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    win = MainWindow()
    win.resize(1200, 700)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
