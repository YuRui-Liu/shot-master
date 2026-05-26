# 去白边：额外向内裁剪（手动 inset）设计

**项目**：drama-shot-master
**版本**：v0.7.x 增量（设计阶段）
**日期**：2026-05-26
**状态**：设计评审通过，待写实现 plan
**关联**：`grid_ops.trim_one/trim_batch` + `trim_panel`。白边 bbox 自动裁由外部 `shot_master.core.aspect_ops.trim_white_edges` 实现。

---

## 1. 背景与目标

bbox 式去白边只能裁掉「整行/整列接近纯白」的边。对带雾气/浅灰渐变边缘的图（非均匀近白），bbox 去不干净，残留浅色边会让生成视频出现白边。需要在自动去白边之后，允许**手动设定四边各自向内再裁 N 像素**来兜底。

### 非目标
- 不改外部 `shot_master` 包（白边 bbox 逻辑不动）
- 不做百分比单位（仅像素）
- 不持久化这些值（与现有 trim 面板 threshold/后缀一致，本就不持久化）
- 不作用于拆图/拼图；不做预览叠加框

---

## 2. 关键决策（评审 Q&A）

| 决策 | 选择 |
|---|---|
| 单位 | 像素（px） |
| 范围 | 上/下/左/右各独立（4 个值） |
| 默认 | 全 0（默认不裁，现有行为不变） |
| 顺序 | 先白边 bbox 裁，再向内裁 |
| 位置 | 本仓库 `grid_ops.trim_one`（白边裁之后），不动外部包 |

---

## 3. 架构

| 改动 | 文件 |
|---|---|
| 新增纯函数 `_inset_crop` + `trim_one`/`trim_batch` 加 4 个 inset 参数 | `drama_shot_master/grid_ops.py` |
| 「额外向内裁剪 (px)」4 个 spinbox + execute 透传 | `drama_shot_master/ui/panels/trim_panel.py` |
| `_inset_crop` 单测 | `tests/test_grid_ops.py` |

`trim_batch` 内部循环调 `trim_one`，故单张/整目录都覆盖。`_inset_crop` 纯 PIL、无外部依赖、可单测。

---

## 4. 详细设计

### 4.1 `_inset_crop`（grid_ops.py 新增）

```python
def _inset_crop(img: Image.Image, top: int = 0, right: int = 0,
                bottom: int = 0, left: int = 0) -> Image.Image:
    """四边各向内裁 N 像素；带钳制，结果至少 1×1，全 0 时原样返回。"""
    w, h = img.size
    top = max(0, top); right = max(0, right)
    bottom = max(0, bottom); left = max(0, left)
    if top == right == bottom == left == 0:
        return img
    x0 = min(left, w - 1)
    y0 = min(top, h - 1)
    x1 = max(w - right, x0 + 1)
    y1 = max(h - bottom, y0 + 1)
    return img.crop((x0, y0, x1, y1))
```
- 负值钳到 0。
- 超量（如 left+right ≥ w）时 `x1 = max(w-right, x0+1)` 保证至少 1px 宽，`y` 同理 → 不出空图、不崩。
- 全 0 → 直接返回原图（不复制、不裁）。

### 4.2 `trim_one` 签名 + 调用

当前：
```python
def trim_one(src_path, out_path, threshold=240, max_iter=5, output_format="PNG") -> Path:
    img = Image.open(src_path)
    trimmed = trim_white_edges(img, threshold=threshold, max_iter=max_iter)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_image(trimmed, out_path, output_format)
    return out_path
```
改为（追加 4 个 inset 参数，默认 0，保持向后兼容）：
```python
def trim_one(src_path, out_path, threshold=240, max_iter=5, output_format="PNG",
             inset_top=0, inset_right=0, inset_bottom=0, inset_left=0) -> Path:
    img = Image.open(src_path)
    trimmed = trim_white_edges(img, threshold=threshold, max_iter=max_iter)
    trimmed = _inset_crop(trimmed, top=inset_top, right=inset_right,
                          bottom=inset_bottom, left=inset_left)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_image(trimmed, out_path, output_format)
    return out_path
```

### 4.3 `trim_batch` 透传

`trim_batch` 加同样 4 个参数（默认 0），在调 `trim_one` 时透传：
```python
def trim_batch(src_folder, out_folder, threshold=240, max_iter=5,
               output_format="PNG", name_suffix="",
               inset_top=0, inset_right=0, inset_bottom=0, inset_left=0) -> list[Path]:
    ...
        trim_one(p, out, threshold=threshold, max_iter=max_iter,
                 output_format=output_format,
                 inset_top=inset_top, inset_right=inset_right,
                 inset_bottom=inset_bottom, inset_left=inset_left)
    ...
```

### 4.4 UI（trim_panel.py）

「去白边参数」表单加一行「额外向内裁剪 (px)」，一个 `QHBoxLayout` 含 4 个紧凑 spinbox（范围 0–2000，默认 0），带「上/下/左/右」小标签：
```python
self.inset_top = _spin(0, 2000, 0)
self.inset_bottom = _spin(0, 2000, 0)
self.inset_left = _spin(0, 2000, 0)
self.inset_right = _spin(0, 2000, 0)
# 一行：上[ ] 下[ ] 左[ ] 右[ ]
```
`execute` 读 4 值，传给 `trim_one`（sel 分支）和 `trim_batch`（整目录分支）。

---

## 5. 数据流

```
[去白边面板：填 上/下/左/右 px + 点执行]
  → trim_one/trim_batch(..., inset_*)
  → trim_white_edges（白边 bbox 自动裁，不变）
  → _inset_crop（四边再向内裁 inset_* px，带钳制）
  → save_image
```

---

## 6. 错误处理 / 边界

| 场景 | 行为 |
|---|---|
| 全 0 | `_inset_crop` 原样返回，等于现有行为 |
| 某边裁剪量过大（≥ 该方向尺寸） | 钳制到至少留 1px，不崩、不空图 |
| 负值（理论上 spinbox 不会给） | 钳到 0 |
| 白边裁后图已很小 | 同样钳制保底 |

---

## 7. 测试

`tests/test_grid_ops.py` 扩展（纯 PIL，无外部依赖）：

| 用例 | 验证 |
|---|---|
| inset_crop_basic | 100×100 纯色图，top=5,right=10,bottom=15,left=20 → 尺寸 (100-20-10)×(100-5-15)=70×80，且裁后区域像素正确 |
| inset_crop_zero_returns_same | 全 0 → 返回同一对象（`is` 原图） |
| inset_crop_overlarge_clamps | left=200,right=200 on 100 宽 → 结果宽 ≥1，不抛异常 |
| inset_crop_negative_clamped | 传负值 → 当 0 处理 |

trim_one/trim_batch 端到端不强测（依赖外部 `shot_master`，其导入已被现有测试覆盖）。

---

## 8. 影响面
- 仅 `grid_ops.py` + `trim_panel.py` + `test_grid_ops.py`
- 零新增依赖
- 向后兼容：4 个参数默认 0，旧调用与行为不变

---

## 9. 不做（YAGNI 清单）
- ❌ 百分比单位
- ❌ 持久化 inset 值
- ❌ 拆图/拼图的向内裁
- ❌ 预览叠加裁剪框
- ❌ 四边统一单值（用户要四边独立）
