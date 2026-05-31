/* Drama-Shot-Master 深色·影视专业主题（蓝紫）
   bg {bg} / navy #13162a / panel #202234 / field #16182a / border #2c2f48
   elevated #262943 / blue {accent} / mauve #a78bfa / periw #8b7fd9
   text {fg} / dim {fg_muted} / faint #5a6076 / done #4ec98f */

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
    color: #5a6076;
}}

/* ---------- 菜单栏 ---------- */
QMenuBar {{
    background-color: #181b2e;
    color: #c9ced4;
    border-bottom: 1px solid #2c2f48;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 12px;
    border-radius: 4px;
    margin: 2px 2px;
}}
QMenuBar::item:selected {{
    background-color: #262943;
    color: {accent_text};
}}
QMenu {{
    background-color: #202234;
    color: {fg};
    border: 1px solid #2c2f48;
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
    background: #2c2f48;
    margin: 4px 8px;
}}

/* ---------- 状态栏 ---------- */
QStatusBar {{
    background-color: #181b2e;
    color: {fg_muted};
    border-top: 1px solid #2c2f48;
}}
QStatusBar::item {{ border: none; }}

/* ---------- 按钮（普通：描边 + 轻填充） ---------- */
QPushButton {{
    background-color: #262943;
    color: {fg};
    border: 1px solid #2c2f48;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 16px;
}}
QPushButton:hover {{
    background-color: #2a2d44;
    border-color: #3a3e5e;
}}
QPushButton:pressed {{
    background-color: #202234;
}}
QPushButton:disabled {{
    background-color: #1f2138;
    color: #5a6076;
    border-color: #2a2d44;
}}
/* checkable 按钮（顶部功能切换 tab）选中态：强调紫(mauve) */
QPushButton:checked {{
    background-color: #a78bfa;
    color: {accent_text};
    border-color: #a78bfa;
    font-weight: 600;
}}
QPushButton:checked:hover {{
    background-color: #b9a3fb;
}}

/* ---------- 主行动按钮（提交/执行）：蓝→紫 渐变 ---------- */
QPushButton#AccentButton {{
    background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {accent}, stop:1 #a78bfa);
    color: {accent_text};
    border: 1px solid transparent;
    font-weight: 600;
    padding: 7px 18px;
}}
QPushButton#AccentButton:hover {{
    background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #6ab0ff, stop:1 #b9a3fb);
    border-color: transparent;
}}
QPushButton#AccentButton:pressed {{
    background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #3d8ae6, stop:1 #8b7fd9);
}}
QPushButton#AccentButton:disabled {{
    background-color: #2f3550;
    color: #6e7290;
    border-color: #2f3550;
}}

/* ---------- 输入控件 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background-color: #16182a;
    color: {fg};
    border: 1px solid #2c2f48;
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
    background-color: #1f2138;
    color: #5a6076;
    border-color: #2a2d44;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: #262943;
    border: none;
    width: 16px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: #3a3e5e;
}}

/* ---------- 下拉框 ---------- */
QComboBox {{
    background-color: #262943;
    color: {fg};
    border: 1px solid #2c2f48;
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 16px;
}}
QComboBox:hover {{ border-color: #3a3e5e; }}
QComboBox:focus {{ border-color: {accent}; }}
QComboBox:disabled {{ background-color: #1f2138; color: #5a6076; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border-left: 1px solid #2c2f48;
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
    background-color: #202234;
    color: {fg};
    border: 1px solid #2c2f48;
    border-radius: 6px;
    outline: none;
    selection-background-color: {accent};
    selection-color: {accent_text};
}}

/* ---------- 列表 ---------- */
QListWidget, QListView, QTreeView, QTableView {{
    background-color: #16182a;
    color: {fg};
    border: 1px solid #2c2f48;
    border-radius: 6px;
    outline: none;
}}
QListWidget::item, QListView::item {{
    padding: 4px;
    border-radius: 4px;
}}
QListWidget::item:hover, QListView::item:hover {{
    background-color: #202234;
}}
QListWidget::item:selected, QListView::item:selected {{
    background-color: {select_bg};
    color: {accent_text};
}}

/* ---------- 表格（任务列表） ---------- */
QTableWidget, QTableView {{
    background-color: #16182a;
    alternate-background-color: #1b1d33;
    gridline-color: #2c2f48;
    border: 1px solid #2c2f48;
    border-radius: 6px;
    outline: none;
}}
QTableWidget::item, QTableView::item {{
    padding: 5px 8px;
    border: none;
}}
QTableWidget::item:hover, QTableView::item:hover {{
    background-color: #232645;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {select_bg};
    color: {accent_text};
}}
QHeaderView {{
    background-color: #202234;
}}
QHeaderView::section {{
    background-color: #202234;
    color: {fg_muted};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #2c2f48;
    border-bottom: 1px solid #2c2f48;
    font-weight: 600;
}}
QHeaderView::section:first {{ border-top-left-radius: 6px; }}
QHeaderView::section:last {{ border-right: none; border-top-right-radius: 6px; }}
QHeaderView::section:hover {{ background-color: #262943; color: {fg}; }}
QTableCornerButton::section {{
    background-color: #202234;
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
    background-color: #16182a;
    border: 1px solid #2c2f48;
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
    background: #2c2f48;
    border-radius: 5px;
    min-height: 28px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: #4a4d72; }}
QScrollBar:horizontal {{
    background: {bg};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #2c2f48;
    border-radius: 5px;
    min-width: 28px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: #4a4d72; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- 复选框 / 单选框 ---------- */
QCheckBox, QRadioButton {{ background: transparent; color: {fg}; spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid #3a3e5e;
    background-color: #16182a;
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
QCheckBox:disabled, QRadioButton:disabled {{ color: #5a6076; }}

/* ---------- 分组框 ---------- */
QGroupBox {{
    background: transparent;
    border: 1px solid #2c2f48;
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
    border: 1px solid #2c2f48;
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background: #1f2138;
    color: {fg_muted};
    border: 1px solid #2c2f48;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: #202234;
    color: {accent_text};
    border-bottom: 2px solid {accent};
}}
QTabBar::tab:hover:!selected {{ color: {fg}; }}

/* ---------- 提示 ---------- */
QToolTip {{
    background-color: #202234;
    color: {fg};
    border: 1px solid {accent};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* ===== 原生外壳：流程侧栏 ===== */
#FlowSidebar {{ background: #13162a; border-right: 1px solid #2c2f48; }}
QLabel#navPhase {{
    color: #7d82a0; font-size: 11px; letter-spacing: 1px;
    padding: 8px 10px 2px 10px;
}}
#FlowSidebar QToolButton {{
    color: #d4d8df; background: transparent; border: none;
    border-radius: 6px; padding: 7px 10px; text-align: left;
}}
#FlowSidebar QToolButton:hover {{ background: #20233a; }}
#FlowSidebar QToolButton:checked,
#FlowSidebar QToolButton[selected="true"] {{
    background: #242748; color: {accent_text};
    border-left: 3px solid #a78bfa;
}}
QToolButton#navCollapse {{ color: {fg_muted}; font-size: 16px; padding: 4px 8px; }}
QFrame#navSep {{ color: #2c2f48; }}

/* ===== 顶部命令栏 ===== */
#ProjectCommandBar {{ background: #181b2e; border-bottom: 1px solid #2c2f48; }}
#ProjectCommandBar QLabel {{ color: #b9bdce; }}
#ProjectCommandBar QPushButton {{
    color: #e6e9ee; background: #262943; border: 1px solid #353a5e;
    border-radius: 6px; padding: 5px 12px;
}}
#ProjectCommandBar QPushButton:hover {{ background: #2f3454; }}

/* ===== 主操作按钮：蓝→紫 渐变 ===== */
QPushButton#AccentButton {{
    color: {accent_text};
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {accent}, stop:1 #a78bfa);
    border: none;
    border-radius: 6px; padding: 6px 16px; font-weight: 600;
}}
QPushButton#AccentButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #6ab0ff, stop:1 #b9a3fb); }}
QPushButton#AccentButton:pressed {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #3d8ae6, stop:1 #8b7fd9); }}

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
        stop:0 {accent}, stop:1 #a78bfa);
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
#WelcomeSettingsBtn:hover {{ background: #262943; }}

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
        stop:0 {accent}, stop:1 #a78bfa);
    border: 1px solid transparent;
    border-radius: 20px;
    padding: 0 30px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1px;
}}
#WelcomeBtnPrimary:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #6ab0ff, stop:1 #b9a3fb); }}
#WelcomeBtnPrimary:pressed {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #3a8adf, stop:1 #8b7fd9); }}

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
QPushButton#AccentButton:disabled {{ background: #2f3550; color: #8b8fa7; }}

/* ---------- 成片合成 ComposePanel ---------- */
#ComposeClipCard {{ background:#13162a; border:1px solid #2c2f48; border-radius:9px; }}
#ComposeClipCard[selected="true"] {{ border:1px solid {accent}; }}
#ComposeClipCard[dropped="true"] {{ background:#0e0e1c; }}
#ComposeClipThumb {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #1a3060, stop:1 #2a2150); border-radius:8px; }}
#ComposeConnector {{ border:1px dashed #3a3e5e; border-radius:15px; min-width:30px; min-height:30px; color:#7a8aaa; background:#13162a; }}
#ComposeConnector[state="ai"] {{ border:2px solid #a78bfa; color:#cdbcf5; }}
#ComposeConnector[state="locked"] {{ border:2px solid #f5a623; color:#f5a623; }}
#ComposeConnector[state="manual"] {{ border:1px solid #3a3e5e; color:#c4cad6; }}
#ComposeConnector[state="plain"] {{ border:1px dashed #3a3e5e; color:#7a8aaa; }}
#ComposeConnector[selected="true"] {{ border:2px solid {accent}; color:#a0c8ff; }}
#ComposeTitle {{ font-size:15px; font-weight:700; color:{fg}; }}
#ComposePrimary {{ color:#fff; border:none; border-radius:18px; padding:8px 18px; font-weight:700;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {accent}, stop:1 #a78bfa); }}

#ComposeRenderBtn {{ color:#a0c8ff; border:1px solid #4a9eff66; border-radius:20px; padding:8px 16px; font-weight:600; background:rgba(74,158,255,0.08); }}
#ComposeRenderBtn:hover {{ background:rgba(74,158,255,0.16); }}
