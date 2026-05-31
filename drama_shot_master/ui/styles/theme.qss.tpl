/* Drama-Shot-Master 深色·影视专业主题
   bg {bg} / panel {bg_alt} / elevated {bg_elevated} / border {border}
   text {fg} / dim {fg_muted} / accent {accent} */

/* ---------- 基础 ---------- */
QWidget {{
    background-color: {bg};
    color: {fg};
    font-size: 10pt;   /* 用 pt 而非 px：避免 pointSize()=-1 触发 QFont setPointSize 警告 */
    selection-background-color: {select_bg};
    selection-color: {accent_text};
}}
QMainWindow, QDialog {{
    background-color: {bg};
}}
QLabel {{
    background: transparent;
    color: {fg};
}}
QLabel:disabled {{
    color: #6b7077;
}}

/* ---------- 菜单栏 ---------- */
QMenuBar {{
    background-color: #232529;
    color: #c9ced4;
    border-bottom: 1px solid {border};
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 12px;
    border-radius: 4px;
    margin: 2px 2px;
}}
QMenuBar::item:selected {{
    background-color: {bg_elevated};
    color: {accent_text};
}}
QMenu {{
    background-color: {bg_alt};
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 16px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {accent};
    color: {accent_text};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 8px;
}}

/* ---------- 状态栏 ---------- */
QStatusBar {{
    background-color: #232529;
    color: {fg_muted};
    border-top: 1px solid {border};
}}
QStatusBar::item {{ border: none; }}

/* ---------- 按钮（普通：描边 + 轻填充） ---------- */
QPushButton {{
    background-color: {bg_elevated};
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 16px;
}}
QPushButton:hover {{
    background-color: #3a3e44;
    border-color: #4a4d52;
}}
QPushButton:pressed {{
    background-color: {bg_alt};
}}
QPushButton:disabled {{
    background-color: #26282b;
    color: #5c6066;
    border-color: #303338;
}}
/* checkable 按钮（顶部功能切换 tab）选中态：强调蓝 */
QPushButton:checked {{
    background-color: {accent};
    color: {accent_text};
    border-color: {accent};
    font-weight: 600;
}}
QPushButton:checked:hover {{
    background-color: #5da9ff;
}}

/* ---------- 主行动按钮（提交/执行）：实心强调蓝 ---------- */
QPushButton#AccentButton {{
    background-color: {accent};
    color: {accent_text};
    border: 1px solid {accent};
    font-weight: 600;
    padding: 7px 18px;
}}
QPushButton#AccentButton:hover {{
    background-color: #5da9ff;
    border-color: #5da9ff;
}}
QPushButton#AccentButton:pressed {{
    background-color: #3d8ae6;
}}
QPushButton#AccentButton:disabled {{
    background-color: #2f3b49;
    color: #6e7d8f;
    border-color: #2f3b49;
}}

/* ---------- 输入控件 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background-color: #1a1b1e;
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {accent};
    selection-color: {accent_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {accent};
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: #232427;
    color: #5c6066;
    border-color: #303338;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: {bg_elevated};
    border: none;
    width: 16px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: #4a4d52;
}}

/* ---------- 下拉框 ---------- */
QComboBox {{
    background-color: {bg_elevated};
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 16px;
}}
QComboBox:hover {{ border-color: #4a4d52; }}
QComboBox:focus {{ border-color: {accent}; }}
QComboBox:disabled {{ background-color: #26282b; color: #5c6066; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border-left: 1px solid {border};
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {fg_muted};
    width: 0; height: 0;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {bg_alt};
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    outline: none;
    selection-background-color: {accent};
    selection-color: {accent_text};
}}

/* ---------- 列表 ---------- */
QListWidget, QListView, QTreeView, QTableView {{
    background-color: #1a1b1e;
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item, QListView::item {{
    padding: 4px;
    border-radius: 4px;
}}
QListWidget::item:hover, QListView::item:hover {{
    background-color: {bg_alt};
}}
QListWidget::item:selected, QListView::item:selected {{
    background-color: {select_bg};
    color: {accent_text};
}}

/* ---------- 表格（任务列表） ---------- */
QTableWidget, QTableView {{
    background-color: #1a1b1e;
    alternate-background-color: #212327;
    gridline-color: #2f3237;
    border: 1px solid {border};
    border-radius: 6px;
    outline: none;
}}
QTableWidget::item, QTableView::item {{
    padding: 5px 8px;
    border: none;
}}
QTableWidget::item:hover, QTableView::item:hover {{
    background-color: #26282c;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {select_bg};
    color: {accent_text};
}}
QHeaderView {{
    background-color: {bg_alt};
}}
QHeaderView::section {{
    background-color: {bg_alt};
    color: {fg_muted};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    font-weight: 600;
}}
QHeaderView::section:first {{ border-top-left-radius: 6px; }}
QHeaderView::section:last {{ border-right: none; border-top-right-radius: 6px; }}
QHeaderView::section:hover {{ background-color: {bg_elevated}; color: {fg}; }}
QTableCornerButton::section {{
    background-color: {bg_alt};
    border: none;
}}

/* ---------- 分隔条 ---------- */
QSplitter::handle {{
    background-color: {bg};
}}
QSplitter::handle:horizontal {{ width: 4px; }}
QSplitter::handle:vertical {{ height: 4px; }}
QSplitter::handle:hover {{ background-color: {accent}; }}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background-color: #1a1b1e;
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    color: {fg};
    height: 16px;
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 5px;
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: {bg};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 5px;
    min-height: 28px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: #4a4d52; }}
QScrollBar:horizontal {{
    background: {bg};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {border};
    border-radius: 5px;
    min-width: 28px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: #4a4d52; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- 复选框 / 单选框 ---------- */
QCheckBox, QRadioButton {{ background: transparent; color: {fg}; spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid #4a4d52;
    background-color: #1a1b1e;
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {accent};
}}
QCheckBox::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}
QRadioButton::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}
QCheckBox:disabled, QRadioButton:disabled {{ color: #5c6066; }}

/* ---------- 分组框 ---------- */
QGroupBox {{
    background: transparent;
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: {fg_muted};
}}

/* ---------- Tab ---------- */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background: #26282b;
    color: {fg_muted};
    border: 1px solid {border};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {bg_alt};
    color: {accent_text};
    border-bottom: 2px solid {accent};
}}
QTabBar::tab:hover:!selected {{ color: {fg}; }}

/* ---------- 提示 ---------- */
QToolTip {{
    background-color: {bg_alt};
    color: {fg};
    border: 1px solid {accent};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* ===== 原生外壳：流程侧栏 ===== */
#FlowSidebar {{ background: #16171a; border-right: 1px solid #24262b; }}
QLabel#navPhase {{
    color: #7d828c; font-size: 11px; letter-spacing: 1px;
    padding: 8px 10px 2px 10px;
}}
#FlowSidebar QToolButton {{
    color: #d4d8df; background: transparent; border: none;
    border-radius: 6px; padding: 7px 10px; text-align: left;
}}
#FlowSidebar QToolButton:hover {{ background: #20232a; }}
#FlowSidebar QToolButton:checked,
#FlowSidebar QToolButton[selected="true"] {{
    background: #1d2a36; color: {accent_text};
    border-left: 3px solid #2563EB;
}}
QToolButton#navCollapse {{ color: {fg_muted}; font-size: 16px; padding: 4px 8px; }}
QFrame#navSep {{ color: #24262b; }}

/* ===== 顶部命令栏 ===== */
#ProjectCommandBar {{ background: #1b1d22; border-bottom: 1px solid #24262b; }}
#ProjectCommandBar QLabel {{ color: #b9bdc6; }}
#ProjectCommandBar QPushButton {{
    color: #e6e9ee; background: #2a2d34; border: 1px solid #353941;
    border-radius: 6px; padding: 5px 12px;
}}
#ProjectCommandBar QPushButton:hover {{ background: #333741; }}

/* ===== 主操作蓝按钮 ===== */
QPushButton#AccentButton {{
    color: {accent_text}; background: #2563EB; border: none;
    border-radius: 6px; padding: 6px 16px; font-weight: 600;
}}
QPushButton#AccentButton:hover {{ background: #2f6df0; }}
QPushButton#AccentButton:pressed {{ background: #1f55c8; }}

/* ═══════════════════════════════════════════════════
   欢迎首页
   ═══════════════════════════════════════════════════ */

/* 容器透明：让 WelcomePage.paintEvent 的渐变+光晕透出
   （否则全局 QWidget{{background-color:bg}} 会用 #1e1f22 灰底盖住渐变） */
#WelcomeHero, #WelcomeCardsArea, #WelcomePagination {{
    background: transparent;
}}

#WelcomeNavBar {{
    background: {welcome_nav_bg};
    border-bottom: 1px solid {welcome_nav_border};
}}

#WelcomeAppIcon {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 {accent}, stop:1 #a06cff);
    border-radius: 5px;
}}

#WelcomeAppName {{
    color: {welcome_app_name_fg};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
}}

#WelcomeSettingsBtn {{
    color: {fg_muted};
    background: rgba(26,26,50,0.8);
    border: 1px solid {welcome_btn_secondary_border};
    border-radius: 5px;
    padding: 0 10px;
    font-size: 11px;
}}
#WelcomeSettingsBtn:hover {{ background: {bg_elevated}; }}

#WelcomeTitle {{
    color: {welcome_title_fg};
    font-size: 28px;
    font-weight: 900;
    letter-spacing: 1px;
}}

#WelcomeSubtitle {{
    color: {welcome_subtitle_fg};
    font-size: 12px;
    letter-spacing: 3px;
}}

#WelcomeBtnPrimary {{
    color: white;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {accent}, stop:1 #a06cff);
    border: 1px solid transparent;
    border-radius: 20px;
    padding: 0 30px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1px;
}}
#WelcomeBtnPrimary:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #6ab0ff, stop:1 #b07fff); }}
#WelcomeBtnPrimary:pressed {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #3a8adf, stop:1 #8a5ccf); }}

#WelcomeBtnSecondary {{
    color: {welcome_btn_secondary_fg};
    background: {welcome_btn_secondary_bg};
    border: 1px solid {welcome_btn_secondary_border};
    border-radius: 20px;
    padding: 0 24px;
    font-size: 13px;
}}
#WelcomeBtnSecondary:hover {{ background: rgba(30,30,60,0.8); }}

#WelcomeEmptyHint {{
    color: {fg_muted};
    font-size: 14px;
}}

#PageDot {{
    background: {welcome_page_dot};
    border-radius: 3px;
}}

#PageDotActive {{
    background: {welcome_page_dot_active};
    border-radius: 3px;
}}
QPushButton#AccentButton:disabled {{ background: #2a3550; color: #8b93a7; }}

/* ---------- 成片合成 ComposePanel ---------- */
#ComposeClipCard {{ background:#12122a; border:1px solid #252540; border-radius:9px; }}
#ComposeClipCard[selected="true"] {{ border:1px solid {accent}; }}
#ComposeClipCard[dropped="true"] {{ background:#0e0e1c; }}
#ComposeClipThumb {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #1a3060, stop:1 #2a1850); border-radius:8px; }}
#ComposeConnector {{ border:1px dashed #3a3a5a; border-radius:15px; min-width:30px; min-height:30px; color:#7a8aaa; background:#10122a; }}
#ComposeConnector[selected="true"] {{ border:2px solid {accent}; color:#a0c8ff; }}
#ComposeTitle {{ font-size:15px; font-weight:700; color:{fg}; }}
#ComposePrimary {{ color:#fff; border:none; border-radius:18px; padding:8px 18px; font-weight:700;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {accent}, stop:1 #a06cff); }}
