"""统一设置页的 SectionWidget 集合。每个 section 自带类属性 title/category 与
load_from/save_to/validate 三个方法，由 UnifiedSettingsDialog 编排。"""

from .runninghub_section import RunningHubSection
from .llm_platforms_section import LLMPlatformsSection
from .translation_section import TranslationSection
from .refine_section import RefineSection
from .imggen_section import ImgGenSection
from .dub_section import DubSection
from .soundtrack_section import SoundtrackSection
from .screenwriter_section import ScreenwriterSection
from .theme_section import ThemeSection

__all__ = [
    "RunningHubSection", "LLMPlatformsSection",
    "TranslationSection", "RefineSection",
    "ImgGenSection", "DubSection", "SoundtrackSection",
    "ScreenwriterSection", "ThemeSection",
]
