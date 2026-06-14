import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# JSON 文件路径
JSON_PATH = Path(
    "/Users/gaoheyang/Desktop/python/AI/xhs_ai/scripts/output/publish_task.json"
)

# 持久化浏览器目录（保存登录状态）
USER_DATA_DIR = (
    "/Users/gaoheyang/Desktop/python/AI/xhs_ai/browser_profile/toutiao"
)

# 读取 JSON
data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

title = data["title"]
content = data["content"]

with sync_playwright() as p:

    # 启动持久化浏览器
    context = p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=False,
        viewport={"width": 1440, "height": 900}
    )

    page = context.new_page()

    # 打开头条发布页面
    page.goto(
        "https://mp.toutiao.com/profile_v4/graphic/publish",
        wait_until="domcontentloaded"
    )

    # 第一次登录需要手动操作
    input(
        "第一次需要登录。登录并进入发布文章页面后，回到终端按回车..."
    )

    # 等待页面稳定
    page.wait_for_load_state("networkidle")

    print("开始填写标题...")

    # 标题输入框
    title_box = page.locator(
        "input[placeholder*='标题'], textarea[placeholder*='标题']"
    ).first

    title_box.wait_for(state="visible", timeout=30000)

    title_box.click()

    # 清空
    title_box.press("Meta+A")
    title_box.press("Backspace")

    # 输入标题
    title_box.fill(title)

    print("标题填写完成")

    print("开始填写正文...")

    # 正文编辑器
    content_box = page.locator(
        "[contenteditable='true']"
    ).first

    content_box.wait_for(state="visible", timeout=30000)

    content_box.click()

    # 清空正文
    content_box.press("Meta+A")
    content_box.press("Backspace")

    # 输入正文
    content_box.fill(content)

    print("正文填写完成")

    print("请检查页面内容")

    input("确认无误后，请手动点击发布。完成后按回车关闭浏览器...")

    context.close()
