# Chinese Econ JMC · 中国经济学博士 Job Market Candidates 名录

一个按年度更新、可多人共同维护的静态网站，收录**美国和加拿大院校**中来自中国大陆的经济学博士 Job Market Candidates 信息（院校、研究领域、JMP、个人主页、去向）。灵感来自 [econ.now/jmc](https://econ.now/jmc/2025)。

- **数据源**：`data/<周期>.md`，每个求职周期一个文件，格式就是我们一直在用的 markdown 写法（见下）。
- **构建**：`scripts/build.py` 把 markdown 解析成 `site/data.js`。
- **网站**：`site/` 目录是纯静态页面（HTML + CSS + JS，无框架），支持按年度 / 地区 / 院校 / 研究领域 / 去向筛选、全文搜索、按院校分组展示、点击展开简介与教育经历，筛选条件会写进 URL 方便分享。
- **部署**：推送到 GitHub 后，GitHub Actions 自动构建并发布到 GitHub Pages。

---

## 一、本地预览

```bash
python scripts/build.py        # 解析 data/*.md -> site/data.js（会打印解析统计和警告）
python -m http.server 8000 -d site
```

然后打开 <http://localhost:8000>。也可以直接双击 `site/index.html`（数据内嵌在 `data.js` 里，不需要服务器）。

## 二、发布到 GitHub Pages（只需做一次）

1. 在 GitHub 新建一个仓库（本项目使用组织 `chinese-econ-jmc` 下的仓库 `chinese-econ-jmc.github.io`，这样网址就是组织名根域）。
2. 在本地推送：
   ```bash
   git remote add origin https://github.com/chinese-econ-jmc/chinese-econ-jmc.github.io.git
   git push -u origin main
   ```
3. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**。
4. 等 Actions 跑完（约 1 分钟），网站地址是 `https://chinese-econ-jmc.github.io/`。
5. 把 `site/app.js` 顶部 `CONFIG.repoUrl` 改成你的仓库地址，页脚的"补充 / 纠错"链接和条目里的"编辑此条目"链接就会指向仓库。

之后每次 `data/` 有改动并推送到 `main`，网站会自动重新构建。

## 三、邀请别人一起维护

**方式 A（推荐，直接协作）**：仓库 **Settings → Collaborators → Add people**，对方接受后可以直接在 GitHub 网页上编辑 `data/*.md` 并提交（Commit changes），几十秒后网站自动更新，不需要装任何东西。

**方式 B（审核制）**：对方 fork 仓库、修改后发 Pull Request，你审核后合并。适合不太熟的贡献者。

**方式 C（不会用 GitHub 的人）**：让他们在仓库里开 Issue 提供信息，由维护者录入。

建议在仓库开启 **Settings → Branches → Branch protection**（要求 PR 才能改 `main`）如果协作者较多。

## 四、数据格式（`data/<周期>.md`）

新周期直接复制 `data/_template.md` 为 `data/2027-2028.md` 即可，网站会自动多出一个年度标签。网站只收录美国和加拿大院校，其他地区院校不录入（另在 Notion 中统计）。格式要点：

```markdown
### 美国区域                                  <- 地区标题（### 开头）

**[#1] Harvard（哈佛大学）**                   <- 院校标题：**[#排名] 英文名（中文名）**，排名可以写 [#?] 或省略

**Xinyue Lin**：她于2018年在北京大学取得经济学学士学位，……预计将于2025年在哈佛大学取得经济学博士学位。她的研究兴趣包括宏观、劳动、行为、发展等领域，她的JMP题为“Employers' Information Advantages over Employees”。

个人主页：https://xinyue-lin.com/

**Placement: Assistant Professor, XXX University**

**Runjiu Liu（刘闰玖）**：她于……            <- 名字后括号内写中文名，可省略

**[#4] Princeton（普林斯顿大学）**

No Chinese in 2025-2026 Cycle.                <- 院校下没有人时可写一句说明，会显示在院校标题旁

### 加拿大区域

**UBC（英属哥伦比亚大学）**                     <- 加拿大院校一般不写排名
```

解析器会从简介段落里自动提取（不需要单独填写）：

| 字段 | 依据 |
|---|---|
| 教育经历 | `YYYY年在XX取得YY学位` |
| 博士毕业年份 | `预计将于YYYY年在XX取得…博士学位` |
| 研究领域标签 | `研究兴趣包括/为/主要是 …` 之后的文字，按 `、和与及` 拆分，再按 `data/fields.json` 里的关键词映射到英文类别（Labor / Macro / IO …） |
| JMP 题目 | `JMP题为“…”` |
| 去向类别 | Placement 文字里含 of Instruction / Teaching / Visiting AP / Clinical / Adjunct，或美国与加拿大的 Lecturer → 非终身轨教职；含 Professor / AP / Lecturer → 教职；Postdoc → 博后；含"延期"→ 延期；其他 → 业界/其他 |
| 教职地区 | 教职的最终任职机构按 `data/regions.json` 里的关键词归到地区（中国大陆 / 港澳 / 美国 / 欧洲 …），用于统计页（stats.html）的地区图表；业界去向按 `data/industry.json` 归到雇主与类别（科技公司 / 金融机构 / 经济咨询 / 政府与国际组织），并按职位名称归到职位类型（数据科学 / 经济学家 / 量化 / 咨询）；机构名称按 `data/institutions.json` 归并（如 RUC / Renmin University → 中国人民大学），用于"主要教职去向机构"。出现新机构时 `build.py` 会提示补关键词 |

**几点约定**（解析器对这些都能容错，但保持一致最省事）：

- 名字后的冒号用中文全角 `：`，英文 `:` 也可以；名字加不加 `**` 都行。
- 一个人的简介写在一段里，不要中途换行；如果不小心换了行，解析器会把它接到上一段。
- 信息暂缺的可以写 `Name：信息不详` 或只写 `Name：`，会标记为"信息不详"。
- `个人主页：` 和 `**Placement: …**` 各占一行，紧跟在该候选人简介之后。
- 自动归类的研究领域不准时，可在该候选人条目下加一行 `研究领域：Macro, Trade`（类别名用 `data/fields.json` 里的名称，逗号分隔），以这一行为准，简介原文不变。
- 新增研究领域关键词请改 `data/fields.json`；运行 `build.py` 时会列出没匹配到任何类别的研究兴趣文字。

运行 `python scripts/build.py --check` 可以只做解析检查不生成文件（GitHub Actions 里的 PR 检查也用它）。

## 五、目录结构

```
data/            每个周期一个 .md（数据源，协作者只需要改这里）+ fields.json（领域关键词）+ regions.json（教职机构 → 地区）+ institutions.json（教职机构名称归并）
scripts/build.py 解析脚本（Python 3.10+，无第三方依赖）
site/            网站静态文件（index.html 名录、stats.html 统计页）；data.js / data.json 由 build.py 生成，不入库
.github/workflows/deploy.yml   push 到 main 时自动构建并发布到 GitHub Pages
```

## 六、隐私说明

网站只收录候选人本人公开在个人主页 / 院系页面上的信息。若有人希望修改或删除自己的条目，请在仓库开 Issue 或直接提交修改。
