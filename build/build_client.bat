@echo off
REM Drama-Shot-Master Client - Nuitka standalone build (no source leakage)
REM Requires: pip install nuitka  (MSVC or clang recommended)
REM
REM Included packages:
REM   - drama_shot_master   GUI main app
REM   - screenwriter_agent  Screenwriter Agent (FastAPI; launched as subprocess
REM                          via `--run-agent screenwriter` flag)
REM   - sound_track_agent   Soundtrack/SFX (demucs/librosa are lazy-imported;
REM                          not bundled by default - add --include-package=librosa if needed)
REM   - uvicorn             ASGI server for agents (dynamic import, explicit include)
REM   - prompt templates + assets (see --include-data-dir below)
REM
REM Excluded (avoid leakage / size):
REM   - license_admin       license management (private key logic) -> --nofollow-import-to
REM   - tests               test code                              -> --nofollow-import-to
REM   - .env / settings.json (api_key, project paths): loose files at repo root,
REM     not inside any package, Nuitka won't include them automatically.
REM     Do NOT add them via --include-data-file.
REM
REM Heavy transitive deps blocked (not needed at runtime):
REM   torch/numba/mcp/google.genai/IPython/demucs/librosa/matplotlib/pandas etc.

REM --- Python 版本 & 路径检查 ---
python --version 2>NUL || (echo [ERROR] python not found in PATH && exit /b 1)
python -c "import sys; v=sys.version_info; assert (v.major,v.minor)>=(3,10), str(v)" 2>NUL
if errorlevel 1 (
    for /f "delims=" %%v in ('python -c "import sys; print(sys.version)"') do echo [ERROR] 需要 Python ^>=3.10，当前版本: %%v
    for /f "delims=" %%p in ('python -c "import sys; print(sys.executable)"') do echo [ERROR] 当前 python: %%p
    echo 请激活正确的环境（如 drama_work）再重试
    exit /b 1
)
for /f "delims=" %%p in ('python -c "import sys; print(sys.executable)"') do echo [OK] Python: %%p

python -m nuitka ^
  --standalone ^
  --enable-plugins=pyside6 ^
  --include-package=drama_shot_master ^
  --include-package=screenwriter_agent ^
  --include-package=sound_track_agent ^
  --include-package=uvicorn ^
  --nofollow-import-to=license_admin ^
  --nofollow-import-to=tests ^
  --nofollow-import-to=torch ^
  --nofollow-import-to=torchvision ^
  --nofollow-import-to=torchaudio ^
  --nofollow-import-to=numba ^
  --nofollow-import-to=llvmlite ^
  --nofollow-import-to=demucs ^
  --nofollow-import-to=librosa ^
  --nofollow-import-to=IPython ^
  --nofollow-import-to=ipykernel ^
  --nofollow-import-to=ipywidgets ^
  --nofollow-import-to=notebook ^
  --nofollow-import-to=jupyter ^
  --nofollow-import-to=jupyter_client ^
  --nofollow-import-to=jupyter_core ^
  --nofollow-import-to=mcp ^
  --nofollow-import-to=google.genai ^
  --nofollow-import-to=google.ai ^
  --nofollow-import-to=anthropic ^
  --nofollow-import-to=langchain ^
  --nofollow-import-to=langchain_core ^
  --nofollow-import-to=langchain_openai ^
  --nofollow-import-to=transformers ^
  --nofollow-import-to=huggingface_hub ^
  --nofollow-import-to=diffusers ^
  --nofollow-import-to=accelerate ^
  --nofollow-import-to=matplotlib ^
  --nofollow-import-to=pandas ^
  --nofollow-import-to=scipy ^
  --nofollow-import-to=sklearn ^
  --nofollow-import-to=skimage ^
  --nofollow-import-to=cv2 ^
  --nofollow-import-to=tensorflow ^
  --nofollow-import-to=keras ^
  --nofollow-import-to=jax ^
  --nofollow-import-to=flax ^
  --nofollow-import-to=xgboost ^
  --nofollow-import-to=lightgbm ^
  --nofollow-import-to=pytest ^
  --nofollow-import-to=_pytest ^
  --nofollow-import-to=sphinx ^
  --nofollow-import-to=docutils ^
  --module-parameter=numba-disable-jit=yes ^
  --include-data-dir=templates=templates ^
  --include-data-dir=drama_shot_master/templates=drama_shot_master/templates ^
  --include-data-dir=drama_shot_master/assets=drama_shot_master/assets ^
  --include-data-dir=drama_shot_master/ui/styles=drama_shot_master/ui/styles ^
  --include-data-dir=screenwriter_agent/templates=screenwriter_agent/templates ^
  --windows-icon-from-ico=drama_shot_master/assets/app_icon.ico ^
  --windows-console-mode=disable ^
  --output-dir=build/dist ^
  drama_shot_master/main.py
echo Done. Output: build/dist/main.dist/
