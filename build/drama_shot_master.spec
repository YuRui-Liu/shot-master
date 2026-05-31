# -*- mode: python ; coding: utf-8 -*-
"""Drama-Shot-Master 客户端 PyInstaller 打包配置（onedir）。

与 Nuitka 版（build_client.bat）同口径：
  打包 = GUI(drama_shot_master) + 编剧 Agent(screenwriter_agent)
         + 配乐(sound_track_agent) + uvicorn + 提示词模板 + 资源
  排除 = license_admin / tests / 个人配置(api_key 等) / 一堆重依赖

打包后编剧 Agent 由同一 exe 以 `--run-agent screenwriter` 启动
（PyInstaller 设 sys.frozen → lifecycle._is_frozen() 命中，见 main._maybe_run_agent）。

运行：build/build_client_pyinstaller.bat（内部 `pyinstaller build/drama_shot_master.spec`）。
说明：PyInstaller 的 .pyc 可被解包反编译；要防源码泄露请用 Nuitka 版。
"""
import os

from PyInstaller.utils.hooks import collect_submodules

# SPECPATH = 本 .spec 所在目录(build/)；ROOT = 仓库根
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

# 顶层包：drama_shot_master 由 main 静态可达；screenwriter_agent 经 __main__
# 在 --run-agent 分支内 lazy import，sound_track_agent 部分入口也 lazy → 显式声明。
hiddenimports = [
    "screenwriter_agent",
    "screenwriter_agent.__main__",
    "screenwriter_agent.server",
    "sound_track_agent",
    # cv2 / scenedetect：compose-cv-v2 自动转场依赖，动态加载不被 PyInstaller 自动追踪
    # Nuitka 版需同步添加：--include-package=cv2 --include-package=scenedetect
    "cv2",
    "scenedetect",
    "platformdirs.windows",
]
# uvicorn 大量动态导入（loop / protocol / lifespan 自动选择）→ 收全子模块
hiddenimports += collect_submodules("uvicorn")

# 随包 ffmpeg/ffprobe（assets/bin/）。
# 有文件才加入；源码签出时缺失也不报错，spec 仍可正常解析。
_ffmpeg_bin = []
for _exe in ("ffmpeg.exe", "ffprobe.exe"):
    _p = os.path.join(ROOT, "drama_shot_master", "assets", "bin", _exe)
    if os.path.exists(_p):
        _ffmpeg_bin.append((_p, os.path.join("assets", "bin")))

# 提示词模板 + 资源（(源路径, 包内目标路径)）
datas = [
    (os.path.join(ROOT, "drama_shot_master", "templates"), "drama_shot_master/templates"),
    (os.path.join(ROOT, "drama_shot_master", "assets"), "drama_shot_master/assets"),
    (os.path.join(ROOT, "screenwriter_agent", "templates"), "screenwriter_agent/templates"),
]

# 排除：授权工具 / 测试 / 一堆非运行期重依赖（与 Nuitka --nofollow-import-to 同口径）。
# 个人配置（api_key、项目路径等散落仓库根的文件）本就不在任何包内、
# 也未列入 datas，PyInstaller 不会收录——切勿手工加进 datas。
excludes = [
    "license_admin", "tests",
    "torch", "torchvision", "torchaudio", "numba", "llvmlite",
    "demucs", "librosa",
    "IPython", "ipykernel", "ipywidgets", "notebook",
    "jupyter", "jupyter_client", "jupyter_core",
    "mcp", "anthropic",
    "langchain", "langchain_core", "langchain_openai",
    "transformers", "huggingface_hub", "diffusers", "accelerate",
    "matplotlib", "pandas", "scipy", "sklearn", "skimage",
    "tensorflow", "keras", "jax", "flax", "xgboost", "lightgbm",
    "pytest", "_pytest", "sphinx", "docutils",
]

a = Analysis(
    [os.path.join(ROOT, "drama_shot_master", "main.py")],
    pathex=[ROOT],
    binaries=_ffmpeg_bin,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DramaShotMaster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                # 桌面应用：无控制台窗口
    icon=os.path.join(ROOT, "drama_shot_master", "assets", "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DramaShotMaster",       # 产物文件夹名
)
