"""media_agent — 本地后端服务：imaging/转场/出图/批量/配乐 收口为 FastAPI(REST+SSE)。

GUI Web 重构 M0：后端对 UI 栈不可知(本地 HTTP+SSE, 127.0.0.1+nonce)，
镜像 screenwriter_agent 模式。纯 Python、零 Qt。
"""
__version__ = "0.1.0"
