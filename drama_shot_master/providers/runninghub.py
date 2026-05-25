"""RunningHub HTTP API 客户端 + LTX 工作流提交器。

独立于 vision providers 与 ComfyUIUpscaler——RunningHub 是远端 SaaS，
封装 5 个 endpoint（upload / create / query / download / cancel），
顶层 submit_ltx_task 串成"提交→轮询→下载"。
"""
from __future__ import annotations


class RunningHubUnavailable(Exception):
    """连接失败 / 服务不可达 / 鉴权缺失。调用方可重试或降级。"""


class RunningHubTaskFailed(Exception):
    """任务执行失败（业务错 / FAILED 状态 / 超时 / 取消）。"""


class RunningHubUploadError(Exception):
    """文件上传失败（本地文件不存在 / 上传 HTTP 错 / 上传业务错）。"""


class RunningHubInvalidSpec(Exception):
    """LTXDirectorSpec 校验失败 / submit 入参非法。"""


from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


SegmentType = Literal["image", "text"]


@dataclass(frozen=True)
class LTXSegment:
    """时间轴上的一段画面：本地图片 + 本段 prompt + 本段时长。"""
    local_prompt: str
    length: int                          # 帧数
    image_path: Path | None = None       # None 表示纯文本段（占时长不占图）
    segment_type: SegmentType = "image"
    guide_strength: float = 1.0          # 0.0~1.0
    seg_id: str = ""                     # 空 → builder 兜底生成


@dataclass(frozen=True)
class LTXAudioSegment:
    """时间轴上的一段音频。"""
    audio_path: Path
    start_frame: int
    length_frames: int


@dataclass(frozen=True)
class LTXDirectorSpec:
    """一次 LTX 视频生成提交的完整用户态参数。

    字段语义与 LTXDirector 节点 (id=46) 的 inputs 对齐。
    """
    # 提示词
    global_prompt: str = ""
    use_global_prompt: bool = True

    # 时间轴
    segments: tuple[LTXSegment, ...] = ()
    audio_segments: tuple[LTXAudioSegment, ...] = ()
    use_custom_audio: bool = False

    # 时长 / 帧率
    display_mode: Literal["seconds", "frames"] = "seconds"
    frame_rate: int = 24

    # 分辨率
    resolution_preset: str = "1280x720 (16:9) (横屏)"
    use_custom_resolution: bool = False
    custom_width: int = 1024
    custom_height: int = 1024

    # 采样
    noise_seed: int | None = None        # None = 用模板默认（固定种子）

    # 输出
    filename_prefix: str = "spb_video"
    output_dir: Path = field(default_factory=lambda: Path("./output"))

    # 其他可调
    epsilon: float = 0.5

    def total_length_frames(self) -> int:
        return sum(s.length for s in self.segments)

    def total_length_seconds(self) -> float:
        return self.total_length_frames() / self.frame_rate

    def unique_local_files(self) -> tuple[Path, ...]:
        """所有需要上传的本地资源路径（去重保序）。"""
        seen: set[Path] = set()
        result: list[Path] = []
        for s in self.segments:
            if s.image_path and s.image_path not in seen:
                seen.add(s.image_path)
                result.append(s.image_path)
        for a in self.audio_segments:
            if a.audio_path not in seen:
                seen.add(a.audio_path)
                result.append(a.audio_path)
        return tuple(result)


import httpx


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
        ".mp4": "video/mp4", ".mov": "video/quicktime",
    }.get(ext, "application/octet-stream")


class RunningHubClient:
    """RunningHub OpenAPI 裸客户端：封装鉴权 + 5 个核心端点。

    每个方法对应一次 HTTP 调用；调用方负责把它们编排成业务流程。
    """

    def __init__(self, api_key: str,
                 base_url: str = "https://www.runninghub.cn",
                 request_timeout: float = 30.0):
        if not api_key:
            raise RunningHubUnavailable("RUNNINGHUB_API_KEY 未设置")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=request_timeout)

    # ---------- upload ----------

    def upload_file(self, path: Path) -> str:
        """上传一个本地文件，返回 RunningHub 内部 fileName。"""
        if not path.exists():
            raise RunningHubUploadError(f"文件不存在: {path}")
        url = f"{self.base_url}/openapi/v2/media/upload/binary"
        try:
            with path.open("rb") as f:
                resp = self._client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (path.name, f, _guess_mime(path))},
                )
            if resp.status_code >= 400:
                raise RunningHubUploadError(
                    f"upload HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if data.get("code") != 0:
                msg = data.get("msg") or data.get("message") or ""
                raise RunningHubUploadError(
                    f"upload code={data.get('code')} msg={msg}")
            return data["data"]["fileName"]
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"upload 连接失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise RunningHubUploadError(f"upload 响应异常: {e}") from e

    # ---------- create_task ----------

    def create_task(self, *,
                    workflow_id: str,
                    node_info_list: list[dict] | None = None,
                    webhook_url: str | None = None,
                    add_metadata: bool = True) -> str:
        """提交 ComfyUI 任务（workflowId + nodeInfoList）。

        RunningHub /task/openapi/create 只接受平台已保存的 workflowId，
        不支持提交裸 workflow JSON。返回 taskId（字符串）。
        """
        if not workflow_id:
            raise RunningHubInvalidSpec("create_task 必须传 workflow_id")
        payload: dict = {
            "apiKey": self.api_key,
            "addMetadata": add_metadata,
            "workflowId": workflow_id,
        }
        if node_info_list:
            payload["nodeInfoList"] = node_info_list
        if webhook_url:
            payload["webhookUrl"] = webhook_url

        url = f"{self.base_url}/task/openapi/create"
        try:
            resp = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code >= 400:
                raise RunningHubTaskFailed(
                    f"create_task HTTP {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            if data.get("code") != 0:
                d = data.get("data")
                tips = d.get("promptTips", "")[:300] if isinstance(d, dict) else ""
                raise RunningHubTaskFailed(
                    f"create_task code={data.get('code')} "
                    f"msg={data.get('msg')} tips={tips} "
                    f"raw={resp.text[:800]}")
            return str(data["data"]["taskId"])
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"create_task 连接失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise RunningHubTaskFailed(f"create_task 响应异常: {e}") from e

    # ---------- query_task ----------

    def query_task(self, task_id: str) -> dict:
        """POST /openapi/v2/query 查任务状态。

        V2 端点返回**扁平 dict**（无 code/msg/data 包装）：
            {taskId, status, errorCode, errorMessage, results,
             clientId, promptTips, failedReason, usage, ...}
        status ∈ {QUEUED, RUNNING, SUCCESS, FAILED}。
        results 在 SUCCESS 时是 [{url, outputType}, ...]，否则 null。

        兼容旧 /task/openapi/status 端点：那个会返
        {code:0, msg:"", data:"STATUS_STR" 或 dict}，本方法也认。
        """
        url = f"{self.base_url}/openapi/v2/query"
        try:
            resp = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"taskId": task_id},
            )
            if resp.status_code >= 400:
                raise RunningHubUnavailable(
                    f"query_task HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            # V2 端点：扁平 dict，含 status 字段即合法
            if "status" in data and "code" not in data:
                return data
            # legacy 端点：{code, msg, data} 包装
            if "code" in data:
                if data["code"] != 0:
                    raise RunningHubUnavailable(
                        f"query_task code={data.get('code')} "
                        f"msg={data.get('msg')}")
                d = data.get("data")
                if isinstance(d, str):
                    return {"status": d, "results": None,
                            "errorCode": "", "errorMessage": ""}
                if isinstance(d, dict):
                    return d
            raise RunningHubUnavailable(
                f"query_task 响应形状未知: keys={list(data.keys())}")
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"query_task 连接失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise RunningHubUnavailable(f"query_task 响应异常: {e}") from e

    # ---------- download_file ----------

    def download_file(self, url: str, dest: Path) -> Path:
        """流式下载到 dest（自动创建 parent dir），返回 dest。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise RunningHubUnavailable(
                        f"download HTTP {resp.status_code}")
                with dest.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
            return dest
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"download 连接失败: {e}") from e

    # ---------- cancel_task ----------

    def cancel_task(self, task_id: str) -> None:
        """POST /task/openapi/cancel；best-effort，失败静默吞错。"""
        url = f"{self.base_url}/task/openapi/cancel"
        try:
            self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"apiKey": self.api_key, "taskId": task_id},
            )
        except httpx.HTTPError:
            pass

    # ---------- account_status ----------

    def get_account_status(self) -> dict:
        """POST /uc/openapi/accountStatus — RunningHub 推荐的鉴权探测端点。

        成功返回 data dict（含 remainCoins / remainMoney / currency / apiType 等）；
        鉴权失败或网络错抛 RunningHubUnavailable。

        无需任何业务参数；最轻量的「测试连接」探测路径。
        """
        url = f"{self.base_url}/uc/openapi/accountStatus"
        try:
            resp = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"apikey": self.api_key},
            )
            if resp.status_code >= 400:
                raise RunningHubUnavailable(
                    f"accountStatus HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if data.get("code") != 0:
                raise RunningHubUnavailable(
                    f"accountStatus code={data.get('code')} msg={data.get('msg')}")
            return data.get("data") or {}
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"accountStatus 连接失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise RunningHubUnavailable(f"accountStatus 响应异常: {e}") from e

    # ---------- 生命周期 ----------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RunningHubClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


import json
import secrets
import time


class LTXNodes:
    """LTX 工作流的关键节点 id。模板更新时改这里。"""
    DIRECTOR = "46"
    SAVE_VIDEO = "104"
    NOISE = "132"
    RESOLUTION = "139"


# ID 模式 nodeInfoList 白名单：仅这 11 个 Director 字段允许被覆盖
_DIRECTOR_FIELDS = (
    "global_prompt", "duration_frames", "duration_seconds",
    "timeline_data", "local_prompts", "segment_lengths",
    "use_custom_audio", "frame_rate", "display_mode",
    "guide_strength", "epsilon",
)


def _gen_seg_id() -> str:
    """模仿原 JSON 里的 id 格式：13 位毫秒戳 + 5 位 hex 随机。"""
    ts = int(time.time() * 1000)
    rnd = secrets.token_hex(3)[:5]
    return f"{ts}{rnd}"


class LTXTaskBuilder:
    """LTXDirectorSpec → workflow JSON / nodeInfoList 翻译。

    启动时一次性加载模板并校验关键节点存在；每次 build_* deepcopy 一份新结果。
    """

    def __init__(self, template_path: Path):
        self.template_path = template_path
        with template_path.open(encoding="utf-8") as f:
            self._template: dict = json.load(f)
        for nid in (LTXNodes.DIRECTOR, LTXNodes.SAVE_VIDEO,
                    LTXNodes.NOISE, LTXNodes.RESOLUTION):
            if nid not in self._template:
                raise RunningHubInvalidSpec(
                    f"模板 {template_path} 缺少节点 {nid}")

    # ---------- 私有：spec → LTXDirector inputs ----------

    def _compute_director_params(self, spec: LTXDirectorSpec,
                                  uploaded_files: dict[Path, str]) -> dict:
        segments_payload = self._build_segments_payload(spec, uploaded_files)
        audio_payload = self._build_audio_segments_payload(spec, uploaded_files)
        timeline_data = json.dumps(
            {"segments": segments_payload, "audioSegments": audio_payload},
            ensure_ascii=False,
        )
        total_frames = spec.total_length_frames()
        return {
            "global_prompt": spec.global_prompt if spec.use_global_prompt else "",
            "duration_frames": total_frames,
            "duration_seconds": round(total_frames / spec.frame_rate, 6),
            "timeline_data": timeline_data,
            "local_prompts": " | ".join(s.local_prompt for s in spec.segments),
            "segment_lengths": ",".join(str(s.length) for s in spec.segments),
            "use_custom_audio": spec.use_custom_audio,
            "frame_rate": spec.frame_rate,
            "display_mode": spec.display_mode,
            "guide_strength": ",".join(
                f"{s.guide_strength:.2f}" for s in spec.segments),
            "epsilon": spec.epsilon,
        }

    def _build_segments_payload(self, spec: LTXDirectorSpec,
                                 uploaded_files: dict[Path, str]) -> list[dict]:
        payload: list[dict] = []
        start = 0
        for seg in spec.segments:
            entry: dict = {
                "id": seg.seg_id or _gen_seg_id(),
                "start": start,
                "length": seg.length,
                "prompt": seg.local_prompt,
                "type": seg.segment_type,
            }
            if seg.image_path is not None:
                file_name = uploaded_files[seg.image_path]
                entry["imageFile"] = Path(file_name).name
                entry["imageB64"] = (
                    f"/view?filename={Path(file_name).name}"
                    f"&type=input&subfolder=")
            payload.append(entry)
            start += seg.length
        return payload

    def _build_audio_segments_payload(self, spec: LTXDirectorSpec,
                                       uploaded_files: dict[Path, str]
                                       ) -> list[dict]:
        if not spec.use_custom_audio or not spec.audio_segments:
            return []
        return [{
            "id": _gen_seg_id(),
            "start": a.start_frame,
            "length": a.length_frames,
            "audioFile": Path(uploaded_files[a.audio_path]).name,
        } for a in spec.audio_segments]

    def _apply_resolution(self, inputs: dict, spec: LTXDirectorSpec) -> None:
        inputs["use_custom_resolution"] = spec.use_custom_resolution
        if spec.use_custom_resolution:
            inputs["custom_width"] = spec.custom_width
            inputs["custom_height"] = spec.custom_height
        else:
            inputs["resolution"] = spec.resolution_preset

    def build_node_info_list(self, spec: LTXDirectorSpec,
                              uploaded_files: dict[Path, str]) -> list[dict]:
        """生成 nodeInfoList 数组（ID 模式）。"""
        self._validate(spec, uploaded_files)
        items: list[dict] = []
        params = self._compute_director_params(spec, uploaded_files)
        for fname in _DIRECTOR_FIELDS:
            if fname in params:
                items.append({
                    "nodeId": LTXNodes.DIRECTOR,
                    "fieldName": fname,
                    "fieldValue": params[fname],
                })
        items.append({
            "nodeId": LTXNodes.SAVE_VIDEO,
            "fieldName": "filename_prefix",
            "fieldValue": spec.filename_prefix,
        })
        if spec.noise_seed is not None:
            items.append({
                "nodeId": LTXNodes.NOISE,
                "fieldName": "noise_seed",
                "fieldValue": spec.noise_seed,
            })
        if spec.use_custom_resolution:
            items.extend([
                {"nodeId": LTXNodes.RESOLUTION,
                 "fieldName": "use_custom_resolution", "fieldValue": True},
                {"nodeId": LTXNodes.RESOLUTION,
                 "fieldName": "custom_width", "fieldValue": spec.custom_width},
                {"nodeId": LTXNodes.RESOLUTION,
                 "fieldName": "custom_height", "fieldValue": spec.custom_height},
            ])
        else:
            items.append({
                "nodeId": LTXNodes.RESOLUTION,
                "fieldName": "resolution",
                "fieldValue": spec.resolution_preset,
            })
        # 不覆盖 CreateVideo.audio：它是节点连线(link)而非 widget，nodeInfoList
        # 只能改 widget，覆盖连线会被服务端拒为 code=404 NOT_FOUND。原生音频路由
        # （改接 LTXVAudioVAEDecode）需在 RunningHub 平台上改工作流本身。
        return items

    # ---------- 校验 ----------

    def _validate(self, spec: LTXDirectorSpec,
                   uploaded_files: dict[Path, str]) -> None:
        if not spec.segments:
            raise RunningHubInvalidSpec("至少需要 1 段")
        if not (1 <= spec.frame_rate <= 120):
            raise RunningHubInvalidSpec(
                f"frame_rate 须在 1-120 之间，当前 {spec.frame_rate}")
        for i, s in enumerate(spec.segments):
            if s.length < 1:
                raise RunningHubInvalidSpec(
                    f"段 {i} length<1（{s.length}）")
            if s.image_path is not None and s.image_path not in uploaded_files:
                raise RunningHubInvalidSpec(
                    f"段 {i} 的图片 {s.image_path} 未在 uploaded_files 中")
            if not (0.0 <= s.guide_strength <= 1.0):
                raise RunningHubInvalidSpec(
                    f"段 {i} guide_strength 越界（{s.guide_strength}）")
        if spec.use_custom_audio:
            for j, a in enumerate(spec.audio_segments):
                if a.audio_path not in uploaded_files:
                    raise RunningHubInvalidSpec(
                        f"音频段 {j} {a.audio_path} 未在 uploaded_files 中")


import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)


def submit_ltx_task(client: RunningHubClient,
                    spec: LTXDirectorSpec,
                    builder: LTXTaskBuilder,
                    *,
                    workflow_id: str,
                    webhook_url: Optional[str] = None,
                    upload_progress_cb: Optional[
                        Callable[[int, int, Path], None]] = None,
                    ) -> "LTXTaskHandle":
    """编排一次完整提交：上传 → 构造 nodeInfoList → create_task → 返回句柄。

    RunningHub 仅支持 workflowId + nodeInfoList 提交（不支持裸 workflow JSON）。

    Args:
        workflow_id: 平台已保存的工作流 ID，必填
        webhook_url: 可选；非 None 时透传给 create_task
        upload_progress_cb(done, total, path): 每上传完一个文件回调一次

    Returns:
        LTXTaskHandle，调用方用 .wait_for_result() 等结果。

    Raises:
        RunningHubInvalidSpec / RunningHubUploadError /
        RunningHubUnavailable / RunningHubTaskFailed
    """
    if not workflow_id:
        raise RunningHubInvalidSpec("submit_ltx_task 需要传 workflow_id")

    # 1. 批量上传
    files_to_upload = spec.unique_local_files()
    uploaded: dict[Path, str] = {}
    for i, path in enumerate(files_to_upload):
        uploaded[path] = client.upload_file(path)
        if upload_progress_cb:
            upload_progress_cb(i + 1, len(files_to_upload), path)

    # 2. 构造 nodeInfoList + 提交
    node_info_list = builder.build_node_info_list(spec, uploaded)
    task_id = client.create_task(
        workflow_id=workflow_id,
        node_info_list=node_info_list,
        webhook_url=webhook_url,
    )

    log.info("RunningHub task submitted: %s (segments=%d)",
             task_id, len(spec.segments))
    return LTXTaskHandle(client, task_id, spec, uploaded)


class LTXTaskHandle:
    """提交后的任务句柄。可跨线程传递（client 自己负责线程安全）。"""

    TERMINAL = {"SUCCESS", "FAILED"}

    def __init__(self, client: RunningHubClient, task_id: str,
                 spec: LTXDirectorSpec,
                 uploaded_files: dict[Path, str]):
        self.client = client
        self.task_id = task_id
        self.spec = spec
        self.uploaded_files = uploaded_files

    def status(self) -> str:
        """单次拉取状态，返回 QUEUED/RUNNING/SUCCESS/FAILED。"""
        d = self.client.query_task(self.task_id)
        return d.get("status", "UNKNOWN")

    def wait_for_result(self,
                        timeout: float = 1800.0,
                        poll_interval: float = 8.0,
                        progress_cb: Optional[Callable[[str], None]] = None,
                        cancel_check: Optional[Callable[[], bool]] = None,
                        ) -> Path:
        """阻塞轮询直到终态。SUCCESS 时下载并返回 MP4 路径。

        timeout 超时 → cancel_task + RunningHubTaskFailed("timeout")。
        cancel_check 返 True → cancel_task + RunningHubTaskFailed("cancelled")。
        网络抖动连续 3 次失败 → RunningHubUnavailable。
        SUCCESS 但 results 为空 → RunningHubTaskFailed。
        """
        deadline = time.time() + timeout
        last_status = ""
        consecutive_network_errors = 0

        while time.time() < deadline:
            if cancel_check and cancel_check():
                self.client.cancel_task(self.task_id)
                raise RunningHubTaskFailed(
                    f"task {self.task_id} cancelled by user")

            try:
                d = self.client.query_task(self.task_id)
                consecutive_network_errors = 0
            except RunningHubUnavailable as e:
                consecutive_network_errors += 1
                if consecutive_network_errors >= 3:
                    raise RunningHubUnavailable(
                        f"query_task 连续 3 次失败: {e}") from e
                log.warning("query_task transient error #%d: %s",
                            consecutive_network_errors, e)
                time.sleep(poll_interval)
                continue

            status = d.get("status", "UNKNOWN")
            if status != last_status and status not in self.TERMINAL:
                last_status = status
                if progress_cb:
                    progress_cb(status)

            if status == "SUCCESS":
                return self._download_first_result(d)
            if status == "FAILED":
                raise RunningHubTaskFailed(
                    f"task {self.task_id} FAILED: "
                    f"code={d.get('errorCode')} msg={d.get('errorMessage')}")

            time.sleep(poll_interval)

        self.client.cancel_task(self.task_id)
        raise RunningHubTaskFailed(
            f"task {self.task_id} timeout after {timeout}s")

    def cancel(self) -> None:
        self.client.cancel_task(self.task_id)

    def _download_first_result(self, query_data: dict) -> Path:
        results = query_data.get("results") or []
        if not results:
            raise RunningHubTaskFailed(
                f"task {self.task_id} SUCCESS 但 results 为空")
        first = results[0]
        url = first.get("url")
        if not url:
            raise RunningHubTaskFailed(
                f"task {self.task_id} results[0] 无 url 字段")
        ext = "." + (first.get("outputType") or "mp4").lower().lstrip(".")
        dest = (self.spec.output_dir
                / f"{self.spec.filename_prefix}_{self.task_id}{ext}")
        return self.client.download_file(url, dest)


# ---------- resolve_ helpers ----------

def resolve_api_key(cfg) -> str:
    """settings.json 中已合并的 cfg.runninghub_api_key > 报错。

    .env / settings.json 的优先级合并由 load_config 在加载时完成；
    本函数只读取最终态字段。
    """
    if getattr(cfg, "runninghub_api_key", ""):
        return cfg.runninghub_api_key
    raise RunningHubUnavailable(
        "未配置 RUNNINGHUB_API_KEY（.env 或 settings.json）")


def resolve_template_path(cfg) -> Path:
    """cfg.runninghub_template_path 自定义 > 项目内置 drama_shot_master/templates/ltx_director_v23.json。"""
    custom = getattr(cfg, "runninghub_template_path", "")
    if custom:
        p = Path(custom)
        if not p.exists():
            raise RunningHubInvalidSpec(
                f"settings.json 指定的模板不存在: {p}")
        return p
    builtin = (Path(__file__).resolve().parent.parent
               / "templates" / "ltx_director_v23.json")
    if not builtin.exists():
        raise RunningHubInvalidSpec(f"内置模板缺失: {builtin}")
    return builtin


def resolve_video_output_dir(cfg, state_output_dir: Path | None) -> Path:
    """cfg.video_output_dir > state_output_dir > 报错。"""
    custom = getattr(cfg, "video_output_dir", "")
    if custom:
        return Path(custom)
    if state_output_dir:
        return state_output_dir
    raise RunningHubInvalidSpec(
        "未设置视频输出目录（settings.video_output_dir 或 state.output_dir 至少一个）")
