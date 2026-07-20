"""UI 全流程自验（Playwright，headless）：空态 → 注册系统/评估程序 → 导 YAML 用例
→ 建任务 → 执行 → 运行记录出现。

跑法（前置：MySQL 起着；API 用自检库 EDD_MYSQL_DB=eddplatform_uicheck 起在 :8000；
vite dev 起在 :5173）：
    .venv/bin/python tests/e2e_ui_check.py
文件名不带 test_ 前缀，不进 pytest 默认收集。
"""
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:5173"
SHOTS = Path("/tmp/claude-1000/-mnt-e-Documents-github-eddplatform/"
             "6b7366fd-d418-47c5-b479-c6dafc9009e4/scratchpad")

YAML = """group: guide
role: guide
cases:
  - id: guide_platform_intro
    turns: [{user: "介绍一下平台"}]
    expect:
      judge: {rubric: "介绍准确"}
  - id: guide_saving
    turns: [{user: "省钱办法"}]
    expect:
      tools: [Skill]
"""


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("dialog", lambda d: d.accept())
        page.goto(BASE)

        # 1 全局概览空态
        expect(page.get_by_text("平台是空的")).to_be_visible()
        page.screenshot(path=str(SHOTS / "01-empty-overview.png"))

        # 2 系统管理空态 + 注册系统
        page.locator("nav.nav").get_by_text("系统管理").click()
        expect(page.get_by_text("暂无系统")).to_be_visible()
        page.get_by_role("button", name="＋ 新建系统").click()
        modal = page.locator(".modal")
        modal.get_by_placeholder("chatagent", exact=True).fill("chatagent")
        modal.get_by_placeholder("chatagent 2.3").fill("chatagent 2.3")
        modal.get_by_placeholder("leo").fill("leo")
        modal.get_by_role("button", name="保存").click()
        expect(page.get_by_role("cell", name="chatagent 2.3")).to_be_visible()
        page.screenshot(path=str(SHOTS / "02-system-created.png"))

        # 3 进入系统 → 注册评估程序
        page.get_by_role("button", name="进入").click()
        page.locator("nav.nav").get_by_text("评估程序").click()
        expect(page.get_by_text("暂无评估程序")).to_be_visible()
        page.get_by_role("button", name="＋ 新建评估程序").click()
        modal = page.locator(".modal")
        modal.get_by_placeholder("chatagent 评估").fill("chatagent 评估")
        modal.get_by_placeholder("/mnt/e/Documents/github/chatagent-eval 或 ssh://git@…").fill(
            "/mnt/e/Documents/github/chatagent-eval")
        modal.get_by_placeholder("chatagent-eval", exact=True).fill("chatagent-eval")
        modal.get_by_role("button", name="保存").click()
        expect(page.get_by_role("cell", name="chatagent-eval", exact=True)).to_be_visible()
        page.screenshot(path=str(SHOTS / "03-eval-program.png"))

        # 4 用例库：YAML 导入
        page.locator("nav.nav").get_by_text("用例库").click()
        page.get_by_role("button", name="导入", exact=True).click()
        modal = page.locator(".modal")
        modal.get_by_text("评估 YAML").click()
        modal.locator("textarea").fill(YAML)
        modal.get_by_role("button", name="导入", exact=True).click()
        expect(page.get_by_text("guide_platform_intro")).to_be_visible()
        expect(page.get_by_text("group/guide").first).to_be_visible()
        page.screenshot(path=str(SHOTS / "04-cases-imported.png"))

        # 5 新建任务：默认已带 启动系统+启动评估程序 两条前置条件，填仓库/ref + 勾选用例
        page.locator("nav.nav").get_by_text("评估任务").click()
        expect(page.get_by_text("还没有评估任务")).to_be_visible()
        page.get_by_role("button", name="＋ 新建评估任务").click()
        modal = page.locator(".modal")
        modal.get_by_placeholder("chatagent 2.3-eval guide 冒烟").fill("guide 冒烟")
        expect(modal.locator(".pill", has_text="启动系统").first).to_be_visible()  # 默认第 1 条
        expect(modal.locator(".pill", has_text="启动评估程序").first).to_be_visible()  # 默认第 2 条
        modal.get_by_placeholder("ssh://git@…/chatagent.git 或本地路径").fill(
            "/mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent3")
        modal.get_by_placeholder("2.3-eval", exact=True).fill("2.3-eval")
        # 用例清单：切手动勾选 → 全选 → 已选 2/2
        modal.get_by_text("手动勾选（固定清单）").click()
        modal.get_by_role("button", name="全选").click()
        expect(modal.get_by_text("已选 2 / 2")).to_be_visible()
        modal.get_by_role("button", name="创建任务").click()
        expect(page.get_by_role("cell", name="guide 冒烟")).to_be_visible()
        expect(page.get_by_role("cell", name="勾选 2 条")).to_be_visible()
        page.screenshot(path=str(SHOTS / "05-task-created.png"))

        # 6 执行 → 提示已提交 → 运行记录出现 running
        page.get_by_role("button", name="执行").click()
        expect(page.get_by_text("已提交执行 R-")).to_be_visible(timeout=15000)
        page.locator("nav.nav").get_by_text("运行记录").click()
        expect(page.get_by_text("guide 冒烟")).to_be_visible()
        expect(page.locator(".pill.run").first).to_be_visible()
        page.get_by_role("button", name="详情").click()
        page.screenshot(path=str(SHOTS / "06-run-created.png"), full_page=True)

        browser.close()
        print("UI 自验通过：空态 → 注册 → 导用例 → 建任务 → 执行 → 运行记录，全流程 OK")


if __name__ == "__main__":
    main()
