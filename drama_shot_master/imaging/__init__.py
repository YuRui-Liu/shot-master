"""图像处理核心（自包含，无外部 shot-master 依赖）。

拆图 / 拼图 / 去白边 / 存盘 / 目录加载，供 drama_shot_master.grid_ops 与 UI 调用。
原先复用兄弟项目 shot-master.core，已内化到本包以利打包发布。
"""
