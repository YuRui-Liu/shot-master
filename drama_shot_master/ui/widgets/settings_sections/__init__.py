"""统一设置页的 SectionWidget 集合。每个 section 自带类属性 title/category 与
load_from/save_to/validate 三个方法，由 UnifiedSettingsDialog 编排。"""

from .runninghub_section import RunningHubSection

__all__ = ["RunningHubSection"]
