"""TaskAggregator smoke：跨 3 store + cfg dict 聚合任务记录。"""
from drama_shot_master.core.task_aggregator import TaskAggregator, TaskRecord
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.core.dub_task_store import DubTaskStore
from drama_shot_master.core.imggen_task_store import ImgGenTaskStore


class _MockMgr:
    def __init__(self, statuses):
        self._statuses = statuses
    def get_status(self, tid):
        return self._statuses.get(tid, "空闲")


def _cfg(soundtrack_tasks=()):
    return type("C", (), {"soundtrack_tasks": list(soundtrack_tasks)})()


def test_aggregator_returns_all_kinds():
    vstore = VideoTaskStore(); vstore.add("V1", {})
    dstore = DubTaskStore(); dstore.add("D1", mode="clone", payload={})
    istore = ImgGenTaskStore(); istore.add("I1", payload={})
    cfg = _cfg([{"id": "s1", "name": "S1", "status": "完成", "output": "/tmp/o.mp4"}])

    vmgr = _MockMgr({vstore.all()[0].id: "生成中"})
    dmgr = _MockMgr({dstore.all()[0].id: "失败"})
    imgr = _MockMgr({istore.all()[0].id: "完成"})

    agg = TaskAggregator(cfg, vstore, dstore, istore,
                         managers={"video": vmgr, "dub": dmgr, "imggen": imgr})
    records = agg.snapshot()
    kinds = sorted({r.kind for r in records})
    assert kinds == ["dub", "imggen", "soundtrack", "video"]
    assert len(records) == 4


def test_aggregator_soundtrack_reads_cfg_dict():
    cfg = _cfg([{"id": "s1", "name": "EP1", "status": "失败", "output": ""}])
    agg = TaskAggregator(cfg, VideoTaskStore(), DubTaskStore(), ImgGenTaskStore(),
                         managers={})
    records = agg.snapshot()
    assert len(records) == 1
    r = records[0]
    assert r.kind == "soundtrack" and r.task_id == "s1" and r.name == "EP1"
    assert r.status == "失败" and r.last_result == ""


def test_aggregator_missing_manager_yields_idle():
    vstore = VideoTaskStore(); vstore.add("V", {})
    agg = TaskAggregator(_cfg(), vstore, DubTaskStore(), ImgGenTaskStore(), managers={})
    records = agg.snapshot()
    assert len(records) == 1 and records[0].status == "空闲"


def test_task_record_is_dataclass_like():
    r = TaskRecord(kind="video", task_id="t", name="n", status="空闲", last_result="")
    assert r.kind == "video" and r.task_id == "t"
