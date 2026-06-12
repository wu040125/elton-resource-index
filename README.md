# elton 的资源索引库

一个从 PDF 链接目录整理出来的静态资源导航站。当前版本采用全量公开静态试水模式：清洗后的公开链接会被打包进前端，原作者相关入口、反馈页、协议页等已在数据生成阶段剔除。

## 项目结构

```text
site/                    Vite + React 静态网站
tools/clean_links.py      链接清洗、分类、验证和站点数据生成脚本
data/                    清洗后的统计和公开数据说明
pdfjm_decrypt.py          授权后 PDF 解密、文本和链接提取脚本
pdfjm_capture_readme.md   从抓包到建站的数据处理记录
requirements.txt          Python 依赖
```

## 本地运行静态站

```powershell
cd .\site
npm install
npm run dev
```

生产构建：

```powershell
cd .\site
npm run build
```

构建输出目录：

```text
site/dist
```

## Cloudflare Pages 部署

推荐通过 GitHub 仓库导入 Cloudflare Pages。

配置：

```text
Framework preset: Vite
Root directory: site
Build command: npm run build
Build output directory: dist
Node version: 20
```

## 重新生成站点数据

从 `output.links.txt` 重新生成清洗数据和站点公开数据：

```powershell
.\.venv\Scripts\python.exe .\tools\clean_links.py --input .\output.links.txt --output-dir .\data
```

生成的站点数据：

```text
site/src/data/links.json
site/src/data/stats.json
```

## 提交安全边界

仓库可以公开，但要注意：当前静态站会公开 `site/src/data/links.json` 中的链接数据。

以下文件已通过 `.gitignore` 排除，不应提交：

```text
.venv/
netlog*.json
output*.pdf
output*.txt
output*.tsv
site/node_modules/
site/dist/
data/links.full.*
data/links.review.*
data_preview/
```

如果以后要做付费完整版，不要把付费完整数据放进 `site/src/data` 或 `site/public`。静态站里的 JSON/JS 都能被浏览器下载。
