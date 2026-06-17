# 世界杯预测到小红书发布全流程说明

本文档按当前代码实际流程梳理：先从 `worldcup/` 刷新数据并生成单场预测 JSON，再由 `xhs_ai/` 读取 JSON，生成小红书图文内容，推到首页二次加工，最后通过已登录浏览器预览或发布。

## 一、整体链路

```text
worldcup/main.py
  ↓
下载历史比赛 CSV
  ↓
调用 football-data.org 拉取世界杯赛程
  ↓
清洗历史比赛数据
  ↓
转换赛程为预测用 fixtures.csv
  ↓
逐场构造赛前特征
  ↓
调用文本大模型做有限进球修正
  ↓
泊松分布计算比分、胜平负概率
  ↓
输出 worldcup/data/reports/world_cup_2026/*.json
  ↓
xhs_ai/worldcup_xhs_main.py 或前端世界杯模块
  ↓
读取 worldcup JSON，转换为小红书草稿
  ↓
可选：世界杯专用小编口吻改写
  ↓
审核、保护关键事实、生成封面
  ↓
输出 xhs_ai/output/*_publish.json
  ↓
前端点击“送到主页预览”
  ↓
把世界杯内容放入首页“生成内容”输入框
  ↓
首页再次调用内容生成功能二次加工
  ↓
用户登录后点击“预览发布”
  ↓
浏览器自动填入小红书发布页
  ↓
默认停在确认阶段；如手动打开“自动点击最终发布”，则继续点击发布
```

## 二、第一部分：worldcup 生成预测报告

### 1. 启动入口

入口文件是：

```bash
cd /Users/gaoheyang/Desktop/worldcupxiaohongshu/worldcup
python main.py
```

常用参数：

```bash
python main.py --max-reports 1
python main.py --max-reports 0
python main.py --skip-history-download --skip-fixtures-download
python main.py --request-interval 0
```

含义：

- `--max-reports 1`：默认只生成 1 场。
- `--max-reports 0`：生成全部待预测赛程。
- `--skip-history-download`：不从 GitHub 下载历史比赛，使用本地 `data/raw/international_results.csv`。
- `--skip-fixtures-download`：不调用 football-data.org，使用本地 `data/raw/world_cup_2026_matches.csv`。
- `--request-interval`：每场调用文本接口后的等待秒数。

### 2. `worldcup/main.py` 做了什么

`worldcup/main.py` 是总控文件，分 5 步：

1. 下载历史国家队比赛数据。
   - 默认地址是 GitHub raw CSV。
   - 输出到 `worldcup/data/raw/international_results.csv`。

2. 拉取世界杯赛程。
   - 调用 `football-data.org`。
   - 依赖 `.env` 中的 `FOOTBALL_DATA_TOKEN`。
   - 输出到 `worldcup/data/raw/world_cup_2026_matches.csv`。

3. 清洗历史比赛。
   - 只保留日期、球队、比分有效的已结束比赛。
   - 生成胜平负标签 `H/D/A`。
   - 输出到 `worldcup/data/processed/historical_matches_clean.csv`。

4. 转换赛程。
   - 把 football-data.org 的赛程字段转换成预测脚本需要的结构。
   - 输出到 `worldcup/data/fixtures/world_cup_2026_fixtures.csv`。

5. 生成预测报告。
   - 调用 `generate_world_cup_reports.main()`。
   - 内部会构造球队特征、调用大模型、计算比分概率。
   - 输出到 `worldcup/data/reports/world_cup_2026/`。

代码里还加了日志：

```text
陈工调用了大模型：即将进入世界杯预测报告生成阶段。
```

真正每次请求大模型时，`llm_match_predictor.py` 也会打印：

```text
陈工调用了大模型：model=xxx url=xxx/chat/completions
```

### 3. 数据和报告产物

主要产物如下：

```text
worldcup/data/raw/international_results.csv
worldcup/data/raw/world_cup_2026_matches.csv
worldcup/data/processed/historical_matches_clean.csv
worldcup/data/fixtures/world_cup_2026_fixtures.csv
worldcup/data/reports/world_cup_2026/2026-xx-xx_home_vs_away.json
worldcup/data/reports/world_cup_2026/report_index.json
```

单场 JSON 里最重要的字段：

- `match`：比赛信息，包含球队、阶段、开球时间。
- `prediction`：预测结果，包含比分、胜平负概率、预期进球。
- `model_details`：大模型修正值和修正理由。
- `team_features`：两队近期表现、进球、失球等特征。
- `weather`：天气数据，目前如果没有接入，会是空。
- `content_material`：给后续内容生成用的简短摘要。

### 4. 大模型在 worldcup 中的角色

`worldcup` 中大模型不是直接决定比分。当前逻辑是：

1. 程序先根据历史数据、球队强弱、近期攻防表现计算基础预期进球。
2. 大模型只输出两个小修正值：
   - `home_goal_adjustment`
   - `away_goal_adjustment`
3. 修正值被限制在很小范围内。
4. 程序把基础预期进球和修正值合并。
5. 最后由泊松分布计算比分概率、胜平负概率、大小球概率。

也就是说：大模型只是“微调预期进球”，最终比分仍由程序概率模型算出来。

## 三、第二部分：xhs_ai 生成小红书内容

### 1. 命令行入口：`xhs_ai/worldcup_xhs_main.py`

可以直接运行：

```bash
cd /Users/gaoheyang/Desktop/worldcupxiaohongshu/xhs_ai
python worldcup_xhs_main.py
```

默认行为：

1. 自动从 `../worldcup/data/reports/world_cup_2026/` 找最新单场报告。
2. 生成小红书 publish JSON。
3. 输出到 `xhs_ai/output/<报告名>_publish.json`。
4. 不执行真实发布。

指定某一场：

```bash
python worldcup_xhs_main.py \
  --report ../worldcup/data/reports/world_cup_2026/2026-06-17_austria_vs_jordan.json \
  --image-mode template
```

使用图片接口生成背景：

```bash
python worldcup_xhs_main.py \
  --report ../worldcup/data/reports/world_cup_2026/2026-06-17_austria_vs_jordan.json \
  --image-mode ai \
  --image-provider openai \
  --image-endpoint "https://api.lmuai.com/v1" \
  --image-model gpt-image-1 \
  --image-size "1024x1024" \
  --image-api-key "你的key"
```

### 2. 前端入口：小红书工具箱中的世界杯模块

前端启动入口是：

```bash
cd /Users/gaoheyang/Desktop/worldcupxiaohongshu/xhs_ai
python main.py
```

`xhs_ai/main.py` 创建整个 PyQt 应用，其中：

- 首页是 `HomePage`。
- 工具箱页是 `ToolsPage`。
- 世界杯模块挂在 `ToolsPage` 里，实际页面是 `WorldCupPage`。

世界杯模块里可以：

1. 选择 `worldcup` 生成的单场 JSON。
2. 选择封面模式：
   - 本地模板。
   - 图片接口生成背景。
3. 点击“生成世界杯小红书内容”。
4. 得到标题、正文、封面、publish JSON。
5. 点击“送到主页预览”。

当前“送到主页预览”的逻辑是：

1. 先切回首页。
2. 把世界杯标题和正文作为素材放入首页的“生成内容”输入框。
3. 自动调用首页原本的“生成内容”功能。
4. 首页生成器再次加工内容。
5. 二次加工后的内容和图片进入首页发布区域。

## 四、小红书内容生成内部流程

### 1. 读取并标准化报告

`WorldCupWorkflowAgent` 调用 `WorldCupReportAdapter.load_report()`：

1. 读取 JSON。
2. 校验根节点。
3. 如果 JSON 是 `worldcup` 真实报告格式，就转换成小红书内部统一结构。
4. 校验比赛、比分、概率是否完整。

### 2. 生成基础草稿

`WorldCupReportAdapter.build_post_draft()` 负责拼出基础小红书草稿。

当前草稿包括：

- 开头介绍。
- `【预测事实】` 区块。
- `【赛前看法】` 区块。
- `【叠甲】只是个人看法。`

当前代码里已经把：

- `FACT_BLOCK_END` 设为空，所以不再显示 `【事实结束】`。
- `DISCLAIMER` 设为空。
- `【数据状态】` 被注释掉。
- 风险提示改成了 `【叠甲】只是个人看法。`
- 开球时间会隐藏末尾的 `+0800` / `+08:00`。

### 3. 世界杯专用文案改写

`WorldCupCopyAgent` 负责把 `【赛前看法】` 改写成更自然的中文。

它调用 `LLMService.generate_text()`，提示词要求：

- 把自己当成一个小编。
- 全部中文。
- 不写“AI”“模型”“算法”等词。
- 不编造伤停、首发、排名、赔率。
- 不写必胜、稳赢。
- 不向用户索要更多资料。

注意：它只改写分析段，不负责删除固定模板字段。固定字段要改 `WorldCupReportAdapter`。

### 4. 审核和事实保护

`WorldCupWorkflowAgent` 会调用：

- `ReviewAgent.review()`：检查内容质量。
- `RewriterAgent.rewrite()`：如果评分不够，可尝试改写。
- `WorldCupReportAdapter.validate_protected_facts()`：检查改写是否篡改关键事实。

受保护事实包括：

- 主队、客队。
- 开球时间。
- 阶段。
- 预测比分。
- 预测结果。
- 主胜、平局、客胜概率。

如果改写改错了这些事实，系统会回退到原始草稿。

### 5. 图片生成

`CoverAgent.generate_for_post()` 负责生成图片。

两种模式：

1. `image_mode=template`
   - 使用本地系统模板。
   - 由 `SystemImageTemplateService.generate_post_images()` 渲染封面和内容页。

2. `image_mode=ai`
   - 先通过 `AIImageService.generate_backgrounds()` 调图片接口生成背景。
   - 再把标题和内容排版到背景图上。
   - 支持 `openai`、`kimi`、`custom`、`anthropic`、`deepseek`、`qwen`。

当前世界杯默认只生成 1 张封面。

### 6. 输出 publish JSON

`ContentWorkflowAgent._build_publish_payload()` 统一生成 publish JSON。

主要字段：

- `title`
- `content`
- `images`
- `topic`
- `review`
- `agent_steps`
- `source_type`
- `worldcup_metadata`

这个文件通常输出到：

```text
xhs_ai/output/*_publish.json
```

## 五、首页二次加工和发布

### 1. 送到首页二次加工

世界杯页面点击“送到主页预览”后，调用：

```python
HomePage.generate_from_worldcup_payload(payload)
```

它会把世界杯内容整理成输入：

```text
请基于下面这份世界杯赛前预测素材，重新生成一篇适合小红书发布的中文内容。
要求：保留比赛、比分、概率等关键事实；不要编造伤停、首发、赔率；语气自然一点。
标题：...
正文：...
```

然后调用首页已有的：

```python
HomePage.generate_content()
```

### 2. 首页生成内容

`HomePage.generate_content()` 启动 `ContentGeneratorThread`。

`ContentGeneratorThread` 的逻辑：

1. 优先读取后台配置里的模型配置。
2. 如果配置了可用模型，就调用 `llm_service.generate_xiaohongshu_content()`。
3. 如果模型不可用，默认允许回退到本地备用生成器。
4. 生成标题、正文、封面图、内容图。
5. 通过 `HomePage.update_ui_after_generate()` 填回首页：
   - 标题输入框。
   - 内容输入框。
   - 图片预览区。

### 3. 登录与发布

用户在首页登录小红书后：

1. `BrowserThread` 创建 `XiaohongshuPoster`。
2. `XiaohongshuPoster.initialize()` 初始化浏览器。
3. `XiaohongshuPoster.login()` 登录。
4. 登录成功后，首页保存 poster。

点击首页“预览发布”时：

1. `HomePage.preview_post()` 把标题、正文、图片加入浏览器线程任务队列。
2. `HomePage.preview_post()` 同时读取“自动点击最终发布”开关。
3. 开关默认关闭，因此默认只预览/填充。
4. `BrowserThread` 收到 `preview` 任务。
5. `ContentWorkflowAgent.publish_payload()` 统一包装发布行为。
6. `PublishAgent.publish()` 调用：

```python
poster.post_article(title, content, images, auto_publish=auto_publish)
```

7. `XiaohongshuPoster.post_article()` 打开小红书发布页，上传图片，填写标题和正文。
8. 如果 `auto_publish=False`，默认只是预览/填充，不自动点击最终发布按钮。
9. 如果用户手动打开“自动点击最终发布”，则 `auto_publish=True`，会继续尝试点击最终发布按钮。

这个开关放在首页发布区域，默认关闭，避免误发。

## 六、关键文件职责表

### worldcup 项目

| 文件 | 作用 |
| --- | --- |
| `worldcup/main.py` | 世界杯数据刷新和报告生成总入口。串起下载历史数据、拉取赛程、清洗数据、转换赛程、生成预测报告。 |
| `worldcup/src/football_data_client.py` | 调用 football-data.org 获取世界杯赛程，并保存为 `data/raw/world_cup_2026_matches.csv`。 |
| `worldcup/src/historical_match_loader.py` | 读取、清洗历史国家队比赛 CSV，生成胜平负标签，保存清洗后的历史数据。 |
| `worldcup/src/build_world_cup_fixtures.py` | 把 football-data.org 的赛程 CSV 转换为预测脚本需要的 `world_cup_2026_fixtures.csv`。 |
| `worldcup/src/current_team_feature_builder.py` | 基于历史比赛数据计算当前球队特征，例如近期胜平负、进失球、实力指标等。 |
| `worldcup/src/llm_match_predictor.py` | 大模型辅助预测器。先计算基础预期进球，再调用大模型做有限修正，最后调用比分概率模型。 |
| `worldcup/src/scoreline_predictor.py` | 使用泊松分布计算比分概率、胜平负概率、大小球概率、双方进球概率。 |
| `worldcup/src/generate_world_cup_reports.py` | 批量读取 fixtures，逐场构造特征、调用预测器、保存单场 JSON 和 `report_index.json`。 |
| `worldcup/src/world_cup_teams.py` | 世界杯球队名单和球队名称标准化，防止非世界杯球队进入预测。 |
| `worldcup/src/match_feature_engineering.py` | 比赛特征工程相关逻辑，用于从历史比赛中整理建模特征。 |
| `worldcup/src/open_meteo_client.py` | 天气接口客户端；当前主流程中还没有真正把天气接入预测，报告里天气常为空。 |
| `worldcup/tests/test_refresh_pipeline.py` | 测试 `worldcup/main.py` 总控流程和 football-data 数据转换。 |
| `worldcup/tests/test_world_cup_dataset.py` | 测试世界杯数据集和赛程数据结构。 |

`worldcup/src/huishou/` 目录是回收/旧版逻辑，当前 `worldcup/main.py` 主流程不依赖它，日常运行可不看。

### xhs_ai 世界杯链路

| 文件 | 作用 |
| --- | --- |
| `xhs_ai/main.py` | 小红书助手前端总入口。初始化数据库、配置、主窗口、首页、工具箱、世界杯模块等。 |
| `xhs_ai/worldcup_xhs_main.py` | 命令行总控入口。自动选择最新 worldcup 报告或指定报告，生成小红书 publish JSON。 |
| `xhs_ai/scripts/publish_worldcup.py` | 较早的世界杯 CLI 脚本。必须手动传 `--report`，可构建 publish JSON；预览/发布需要 GUI 注入已登录 poster。 |
| `xhs_ai/src/core/pages/tools.py` | 工具箱页面，把 `WorldCupPage` 挂到前端工具区。 |
| `xhs_ai/src/core/pages/worldcup_page.py` | 世界杯前端页面。选择报告、配置封面模式、生成世界杯内容、送到首页二次加工。 |
| `xhs_ai/src/agents/worldcup_workflow_agent.py` | 世界杯小红书内容编排器。读取报告、生成草稿、改写分析、审核、保护事实、生成图片、输出 payload。 |
| `xhs_ai/src/integrations/worldcup_report_adapter.py` | worldcup JSON 到小红书草稿的适配器。负责字段标准化、中文队名、事实区块、正文模板、开球时间格式、事实校验。 |
| `xhs_ai/src/agents/worldcup_copy_agent.py` | 世界杯赛前分析口语化改写 Agent。调用文字模型把分析写得更像小编。 |
| `xhs_ai/src/agents/cover_agent.py` | 统一生成封面/内容图。支持本地模板、营销海报模板、图片接口背景。 |
| `xhs_ai/src/core/services/ai_image_service.py` | 图片接口服务。按 provider 调不同图片适配器，并把生成结果保存到本地。 |
| `xhs_ai/src/core/ai_integration/custom_image_adapter.py` | OpenAI Images 兼容中转站图片接口适配器。 |
| `xhs_ai/src/core/ai_integration/kimi_adapter.py` | Kimi 或 Kimi 兼容中转站图片接口适配器。 |
| `xhs_ai/src/core/ai_integration/anthropic_image_adapter.py` | Anthropic 兼容网关图片接口适配器。 |
| `xhs_ai/src/core/ai_integration/deepseek_image_adapter.py` | DeepSeek 图片网关适配器，适用于第三方支持生图的兼容接口。 |
| `xhs_ai/src/core/ai_integration/qwen_adapter.py` | 通义万相图片接口适配器。 |
| `xhs_ai/src/core/services/system_image_template_service.py` | 本地系统模板渲染服务。识别 `assets/system_templates/template_showcase/*.png`，生成封面和内容图。 |
| `xhs_ai/src/core/pages/home.py` | 首页。接收世界杯 payload，放入“生成内容”输入框二次加工；也负责预览发布按钮。 |
| `xhs_ai/src/core/processor/content.py` | 首页“生成内容”的后台线程。优先调用配置的大模型生成小红书文案，失败可回退本地备用生成器，并生成图片。 |
| `xhs_ai/src/core/services/llm_service.py` | 文本大模型统一服务。封装普通文案生成、世界杯分析改写、营销海报文案等文本调用。 |
| `xhs_ai/src/agents/workflow_agent.py` | 通用内容工作流。构建 publish payload，并提供 `publish_payload()` 调用发布 Agent。 |
| `xhs_ai/src/agents/publish_agent.py` | 发布 Agent。把标题、正文、图片交给浏览器 poster。 |
| `xhs_ai/src/core/browser.py` | 浏览器线程。维护登录状态、任务队列，处理 preview 和 scheduled publish 任务。 |
| `xhs_ai/src/core/write_xiaohongshu.py` | 实际控制浏览器的小红书发布器。负责打开发布页、上传图片、填写标题正文、预览或最终发布。 |
| `xhs_ai/src/core/processor/img.py` | 图片处理线程。把生成的图片处理成首页预览可用的 pixmap/list。 |
| `xhs_ai/src/config/config.py` | 前端配置读写，包括模型配置、模板配置、手机号区号等。 |
| `xhs_ai/src/config/database.py` / `xhs_ai/src/core/database_manager.py` | 应用启动时初始化和维护数据库。世界杯链路不是重点依赖，但 `xhs_ai/main.py` 启动会检查。 |

### xhs_ai 相关测试

| 文件 | 作用 |
| --- | --- |
| `xhs_ai/tests/test_worldcup_report_adapter.py` | 测试 worldcup JSON 适配、字段校验、事实保护、开球时间格式等。 |
| `xhs_ai/tests/test_worldcup_copy_agent.py` | 测试世界杯分析改写 Agent 的提示词和清洗逻辑。 |
| `xhs_ai/tests/test_worldcup_workflow_agent.py` | 测试世界杯内容完整工作流。 |
| `xhs_ai/tests/test_worldcup_page.py` | 测试世界杯前端页面、图片模式切换、送到首页二次生成。 |
| `xhs_ai/tests/test_worldcup_xhs_main.py` | 测试命令行总控入口自动发现最新报告、传参和输出路径。 |
| `xhs_ai/tests/test_ai_image_service.py` | 测试图片接口适配器和 AI 图片生成服务。 |
| `xhs_ai/tests/test_system_image_template_service.py` | 测试系统模板服务能识别普通 PNG 模板，例如 `ghy.png`。 |

## 七、从零运行建议

### 1. 先生成 worldcup 报告

```bash
cd /Users/gaoheyang/Desktop/worldcupxiaohongshu/worldcup
python main.py --max-reports 1
```

需要确保 `.env` 里至少有：

```text
FOOTBALL_DATA_TOKEN=你的football-data token
LLM_BASE_URL=你的文本模型接口地址
LLM_API_KEY=你的文本模型key
LLM_MODEL=你的文本模型名
```

### 2. 再生成小红书 payload

命令行：

```bash
cd /Users/gaoheyang/Desktop/worldcupxiaohongshu/xhs_ai
python worldcup_xhs_main.py --image-mode template
```

或者打开前端：

```bash
cd /Users/gaoheyang/Desktop/worldcupxiaohongshu/xhs_ai
python main.py
```

进入：

```text
工具箱 → 世界杯预测 → 小红书
```

然后：

1. 选择报告。
2. 选择封面模式。
3. 点击“生成世界杯小红书内容”。
4. 点击“送到主页预览”。
5. 等首页二次生成完成。
6. 登录小红书。
7. 默认保持“自动点击最终发布”关闭。
8. 点击“预览发布”。
9. 浏览器填好发布页后，人工确认最终发布。
10. 如果确认要无人值守发布，再手动打开“自动点击最终发布”，然后点击“预览发布”。

## 八、哪些地方最常改

### 1. 想改世界杯报告生成逻辑

优先看：

- `worldcup/main.py`
- `worldcup/src/generate_world_cup_reports.py`
- `worldcup/src/llm_match_predictor.py`
- `worldcup/src/current_team_feature_builder.py`

### 2. 想改小红书正文结构

改：

- `xhs_ai/src/integrations/worldcup_report_adapter.py`

它控制：

- 标题。
- 预测事实区块。
- 赛前看法。
- 叠甲/风险提示。
- 标签是否显示。
- 开球时间显示格式。

### 3. 想改世界杯“像小编”改写提示词

改：

- `xhs_ai/src/agents/worldcup_copy_agent.py`

注意：这个 Agent 只改 `【赛前看法】` 的文字，不负责删除模板里的固定区块。

### 4. 想改图片样式

本地模板：

- `xhs_ai/assets/system_templates/template_showcase/`
- `xhs_ai/src/core/services/system_image_template_service.py`

AI 图片背景：

- `xhs_ai/src/agents/cover_agent.py`
- `xhs_ai/src/core/services/ai_image_service.py`
- `xhs_ai/src/core/ai_integration/*_adapter.py`

### 5. 想改“送到主页后怎么二次加工”

改：

- `xhs_ai/src/core/pages/home.py` 的 `generate_from_worldcup_payload()`
- `xhs_ai/src/core/pages/worldcup_page.py` 的 `send_to_home()`

### 6. 想改最后浏览器发布动作

改：

- `xhs_ai/src/core/write_xiaohongshu.py`
- `xhs_ai/src/core/browser.py`
- `xhs_ai/src/agents/publish_agent.py`

## 九、当前链路的几个注意点

1. `worldcup` 生成报告会真实调用文本大模型。
2. `xhs_ai` 的世界杯分析改写也会调用文本模型。
3. 点击“送到主页预览”后，首页会再调用一次“生成内容”，所以还会额外调用一次文本模型。
4. 如果首页模型不可用，默认可能回退到本地备用生成器。
5. `worldcup_xhs_main.py` 和 `scripts/publish_worldcup.py` 默认只生成 JSON，不真实发布。
6. 前端首页有“自动点击最终发布”开关，默认关闭。
7. 开关关闭时，“预览发布”只会填充发布页，最终是否发布由用户确认。
8. 开关打开时，“预览发布”会传 `auto_publish=True`，浏览器会尝试点击最终发布按钮。
9. 定时发布或其他显式自动发布流程也可能走 `auto_publish=True`。
