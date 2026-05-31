"""图片生成编辑器：模式自动判定 + 参考图区(@标签) + 画质/比例/数量 + 快捷词 + 生成。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import (
    QPixmap, QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QComboBox, QSpinBox, QScrollArea, QFrame, QInputDialog, QFileDialog,
    QMessageBox, QGridLayout, QSizePolicy,
)


def resolve_imggen_out_dir(cfg) -> Path:
    """出图落盘目录：出图专属目录 > 主面板「输出目录」(last_output_dir) > 当前目录。

    末尾统一加 imggen 子目录。空的出图目录回退到主面板输出目录，
    而非 cwd——否则图会落到程序工作目录，与项目分离。
    """
    base = ((getattr(cfg, "imggen_output_dir", "") or "").strip()
            or (getattr(cfg, "last_output_dir", "") or "").strip()
            or ".")
    return Path(base) / "imggen"


class _AtRefHighlighter(QSyntaxHighlighter):
    """把 @标签 标蓝——仅当标签是当前已添加的参考图标签时才高亮。"""

    def __init__(self, document, accent_color: str = "#4a9eff"):
        super().__init__(document)
        self._labels: list[str] = []
        self._fmt = QTextCharFormat()
        self._fmt.setForeground(QColor(accent_color))
        self._fmt.setFontWeight(QFont.Bold)

    def set_labels(self, labels):
        # 长标签优先，避免 @图1 命中 @图10 前缀
        self._labels = sorted({s for s in labels if s}, key=len, reverse=True)
        self.rehighlight()

    def highlightBlock(self, text: str):
        for lab in self._labels:
            token = "@" + lab
            n = len(token)
            start = 0
            while True:
                i = text.find(token, start)
                if i < 0:
                    break
                end = i + n
                nxt = text[end] if end < len(text) else ""
                if not nxt.isalnum():        # 边界：后接字母/数字则不算(防前缀误匹配)
                    self.setFormat(i, n, self._fmt)
                start = end

from drama_shot_master.config import Config
from drama_shot_master.core.imggen_sizes import QUALITIES, RATIOS, resolve_size
from drama_shot_master.core.imggen_presets import QUICK_PROMPTS
from drama_shot_master.providers.image_gen import make_image_provider, ImageGenError
from drama_shot_master.ui.theme import _tokens, current_theme
from drama_shot_master.ui.worker import FunctionWorker


class ImgGenPanel(QWidget):
    statusChanged = Signal(str)
    resultReady = Signal(str)
    dirty = Signal()

    def __init__(self, cfg: Config, payload: dict | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker = None
        self._refs: list[dict] = []     # [{path,label}]
        self._results: list[str] = []
        self._build_ui()
        if payload:
            self.load_payload(payload)
        self._update_mode()

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.mode_lbl = QLabel("模式：文生图")
        _t = _tokens(current_theme(self.cfg))
        self.mode_lbl.setStyleSheet(f"color:{_t['fg_muted']};")
        root.addWidget(self.mode_lbl)

        # 参考图区
        root.addWidget(QLabel("参考图（点卡片把 @标签 插入提示词）："))
        self.ref_bar = QHBoxLayout()
        add_btn = QPushButton("+ 参考图"); add_btn.clicked.connect(self._add_refs)
        self.ref_bar.addWidget(add_btn)
        self.ref_bar.addStretch(1)
        ref_wrap = QWidget(); ref_wrap.setLayout(self.ref_bar)
        root.addWidget(ref_wrap)

        # 画质/比例/数量
        opt = QHBoxLayout()
        self.quality = QComboBox(); self.quality.addItems(QUALITIES)
        self.ratio = QComboBox(); self.ratio.addItems(RATIOS)
        self.count = QSpinBox(); self.count.setRange(1, 4); self.count.setValue(1)
        # 画质/比例/数量变化也实时存(否则只在关窗时保存)
        self.quality.currentIndexChanged.connect(lambda *_: self.dirty.emit())
        self.ratio.currentIndexChanged.connect(lambda *_: self.dirty.emit())
        self.count.valueChanged.connect(lambda *_: self.dirty.emit())
        for w in (QLabel("画质"), self.quality, QLabel("比例"), self.ratio,
                  QLabel("数量"), self.count):
            opt.addWidget(w)
        opt.addStretch(1)
        root.addLayout(opt)

        # 快捷词按钮
        qrow = QGridLayout()
        for i, (label, text) in enumerate(QUICK_PROMPTS):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, t=text: self._insert(t))
            qrow.addWidget(b, i // 5, i % 5)
        qwrap = QWidget(); qwrap.setLayout(qrow)
        root.addWidget(qwrap)

        self.prompt = QPlainTextEdit(); self.prompt.setPlaceholderText("提示词…")
        self._highlighter = _AtRefHighlighter(self.prompt.document(), _t["accent"])
        self.prompt.textChanged.connect(self._update_mode)
        self.prompt.textChanged.connect(lambda: self.dirty.emit())
        root.addWidget(self.prompt, 1)

        bar = QHBoxLayout()
        self.btn_gen = QPushButton("生成"); self.btn_gen.setObjectName("AccentButton")
        self.btn_gen.clicked.connect(self._generate)
        self.status_lbl = QLabel(""); self.status_lbl.setStyleSheet(f"color:{_t['fg_muted']}")
        # 状态文字不撑窗：忽略内容宽度、允许换行，长报错只进弹窗
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        bar.addWidget(self.btn_gen); bar.addWidget(self.status_lbl, 1)
        root.addLayout(bar)

        self.result_row = QHBoxLayout()
        rwrap = QWidget(); rwrap.setLayout(self.result_row)
        root.addWidget(rwrap)
        self._refresh_refs()

    # ---------- 参考图 ----------
    def _add_refs(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择参考图", "", "图片 (*.png *.jpg *.jpeg *.webp)")
        for p in paths:
            self._refs.append({"path": p, "label": f"图{len(self._refs)+1}"})
        if paths:
            self._refresh_refs(); self._update_mode(); self.dirty.emit()

    def _refresh_refs(self):
        # 清掉除「+参考图」「stretch」外的卡片（保留 index 0 按钮、末尾 stretch）
        while self.ref_bar.count() > 2:
            it = self.ref_bar.takeAt(1)
            w = it.widget()
            if w:
                w.deleteLater()
        for i, r in enumerate(self._refs):
            self.ref_bar.insertWidget(1 + i, self._ref_card(i, r))
        if hasattr(self, "_highlighter"):
            self._highlighter.set_labels([r["label"] for r in self._refs])

    def _ref_card(self, idx: int, r: dict) -> QWidget:
        card = QFrame(); card.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(card); v.setContentsMargins(4, 4, 4, 4)
        thumb = QLabel(); pm = QPixmap(r["path"])
        if not pm.isNull():
            thumb.setPixmap(pm.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        thumb.setFixedSize(72, 72); thumb.setAlignment(Qt.AlignCenter)
        v.addWidget(thumb)
        lab = QPushButton(f"@{r['label']}")
        lab.clicked.connect(lambda _=False, i=idx: self._insert(f"@{self._refs[i]['label']} "))
        v.addWidget(lab)
        row = QHBoxLayout()
        rn = QPushButton("改名"); rn.clicked.connect(lambda _=False, i=idx: self._rename_ref(i))
        rm = QPushButton("×"); rm.clicked.connect(lambda _=False, i=idx: self._remove_ref(i))
        row.addWidget(rn); row.addWidget(rm)
        v.addLayout(row)
        return card

    def _rename_ref(self, i: int):
        name, ok = QInputDialog.getText(self, "改名", "标签:", text=self._refs[i]["label"])
        if ok and name.strip():
            self._refs[i]["label"] = name.strip()
            self._refresh_refs(); self.dirty.emit()

    def _remove_ref(self, i: int):
        self._refs.pop(i)
        self._refresh_refs(); self._update_mode(); self.dirty.emit()

    def _insert(self, text: str):
        self.prompt.insertPlainText(text)

    def _update_mode(self):
        has_ref = bool(self._refs)
        has_txt = bool(self.prompt.toPlainText().strip())
        mode = ("图文生图" if has_ref and has_txt else
                "图生图" if has_ref else "文生图")
        self.mode_lbl.setText(f"模式：{mode}（自动）")

    # ---------- payload ----------
    def to_payload(self) -> dict:
        return {"prompt": self.prompt.toPlainText(), "refs": list(self._refs),
                "quality": self.quality.currentText(), "ratio": self.ratio.currentText(),
                "n": self.count.value()}

    def load_payload(self, p: dict):
        self.prompt.setPlainText(p.get("prompt", ""))
        self._refs = [dict(r) for r in p.get("refs", []) or []]
        qi = self.quality.findText(p.get("quality", "2K")); self.quality.setCurrentIndex(max(0, qi))
        ri = self.ratio.findText(p.get("ratio", "自动")); self.ratio.setCurrentIndex(max(0, ri))
        self.count.setValue(int(p.get("n", 1) or 1))
        self._refresh_refs(); self._update_mode()

    # ---------- 生成 ----------
    def _generate(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            QMessageBox.warning(self, "需要激活", "授权无效或已过期，无法生成。")
            return
        prompt = self.prompt.toPlainText().strip()
        if not prompt and not self._refs:
            QMessageBox.information(self, "提示", "请填写提示词或添加参考图"); return
        cfg = self.cfg
        size = resolve_size(self.quality.currentText(), self.ratio.currentText())
        n = self.count.value()
        refs = [Path(r["path"]) for r in self._refs]
        out_dir = resolve_imggen_out_dir(cfg)
        ts = time.strftime("%Y%m%d_%H%M%S")

        def task():
            provider = make_image_provider(cfg)
            images = provider.generate(prompt, refs, size=size, n=n)
            out_dir.mkdir(parents=True, exist_ok=True)
            paths = []
            for i, data in enumerate(images):
                fp = out_dir / f"img_{ts}_{i+1}.png"
                fp.write_bytes(data)
                paths.append(str(fp))
            return paths

        self.btn_gen.setEnabled(False)
        self.status_lbl.setText("生成中…"); self.statusChanged.emit("RUNNING")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_done(self, paths: list):
        self._results = paths
        self.btn_gen.setEnabled(True)
        self.status_lbl.setText(f"完成：{len(paths)} 张")
        self.statusChanged.emit("SUCCESS")
        if paths:
            self.resultReady.emit(paths[0])
        self._show_results(paths)

    def _on_fail(self, err: str):
        self.btn_gen.setEnabled(True)
        self.status_lbl.setText("生成失败（详见弹窗）")   # 短状态，避免长报错撑窗
        self.statusChanged.emit("FAILED")
        QMessageBox.critical(self, "生成失败", err)

    def _show_results(self, paths: list):
        while self.result_row.count():
            it = self.result_row.takeAt(0); w = it.widget()
            if w:
                w.deleteLater()
        for p in paths:
            lbl = QLabel(); pm = QPixmap(p)
            if not pm.isNull():
                lbl.setPixmap(pm.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl.setToolTip(p)
            self.result_row.addWidget(lbl)
        if paths:
            ob = QPushButton("打开结果"); ob.clicked.connect(lambda: self._open(paths[0]))
            self.result_row.addWidget(ob)
        self.result_row.addStretch(1)

    def _open(self, path: str):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
