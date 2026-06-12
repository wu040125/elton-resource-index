# pdfjm.cn 授权后 PDF 解密与文本提取指南

本文档记录一种通用流程：使用真实 Chrome 完成 pdfjm.cn 分享页的扫码授权，通过 `chrome://net-export/` 导出授权后的网络日志，再用本地脚本自动提取解密参数、下载加密容器、输出明文 PDF 和文本。

脚本只处理你已经有权限访问的分享文件，不绕过微信授权、白名单或访问控制。

## 文件说明

```text
pdfjm_decrypt.py       主脚本
requirements.txt       Python 依赖
netlog.json            Chrome net-export 导出的网络日志，运行时输入
output.pdf             解密后的明文 PDF，运行后输出
output.txt             从 PDF 提取的文本，运行后输出
output.links.txt       从 PDF 提取的链接表，运行后输出
```

## 安装依赖

建议在虚拟环境中安装：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r .\requirements.txt
```

当前依赖包括：

```text
cryptography   PBKDF2 + AES-GCM 解密
requests       下载 CDN 加密容器
pypdf          提取 PDF 文本
playwright     可选浏览器自动化模式
```

如果要尝试 Playwright 模式，还需要：

```powershell
python -m playwright install chromium
```

## 数据清洗与免费/完整版切分

从 PDF 提取链接后，可以先不构建网站，只做数据清洗、分类、验证和免费/完整版切分。

输入文件：

```text
output.links.txt
```

运行：

```powershell
.\.venv\Scripts\python.exe .\tools\clean_links.py --input .\output.links.txt --output-dir .\data
```

输出：

```text
data/links.full.json     完整版数据，后续付费/完整资源库使用
data/links.full.tsv      完整版表格，方便人工审查
data/links.free.json     免费版数据，后续静态站公开展示使用
data/links.free.tsv      免费版表格，方便人工审查
data/links.review.json   需要人工复核的数据
data/links.review.tsv    需要人工复核的表格
data/summary.json        统计汇总
data/README.md           数据处理说明
```

当前免费版策略：

```text
只放验证可访问的公开站点、搜索源、工具站、设计素材、AI 工具、少量教程/学习资料。
不放网盘直链、pdfjm.top 站内资源、前拥有者运营页、反馈页、协议页、明显低质量或当前不可访问链接。
```

当前完整版策略：

```text
保留全部清洗后的链接，包括超时、受限访问、网盘资源、站内资源等，但会标记 status、score、tier、notes，供后续人工筛选。
```

## 静态网站

当前已生成一个 Vite + React + TypeScript 静态资源导航站：

```text
site/
```

站点使用：

```text
site/src/data/links.json
site/src/data/stats.json
```

其中 `links.json` 只包含公开展示数据，不包含完整付费库的 URL。

本地运行：

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

构建输出：

```text
site/dist
```

后续部署到 Cloudflare Pages 时：

```text
Root directory: site
Build command: npm run build
Output directory: dist
```

## 推荐流程：Chrome net-export 模式

这是当前最稳定的方式，因为它使用真实 Chrome 完成扫码授权，避免 Playwright 自动化环境触发网站检测。

### 1. 开始抓包

在真实 Chrome 中打开：

```text
chrome://net-export/
```

选择包含原始字节的记录模式，界面中通常显示为：

```text
Include raw bytes
```

然后点击 `Start Logging`。

### 2. 完成授权访问

在同一个 Chrome 中打开分享链接，例如：

```text
https://pdfjm.cn/#/file/viewer/NTU5MzU3
```

按页面提示微信扫码授权，等 PDF Viewer 正常加载出文档。

### 3. 停止抓包

回到 `chrome://net-export/` 页面，点击 `Stop Logging`，保存为：

```text
netlog.json
```

### 4. 解密并提取文本

在项目目录运行：

```powershell
python .\pdfjm_decrypt.py --netlog .\netlog.json -o .\output.pdf
```

如果已经激活 `.venv`，直接用 `python` 即可；否则可以明确指定虚拟环境解释器：

```powershell
.\.venv\Scripts\python.exe .\pdfjm_decrypt.py --netlog .\netlog.json -o .\output.pdf
```

成功输出类似：

```text
captured CDN URL from netlog: https://cdn.pdfjm.com/...
wrote 5377065 bytes to output.pdf
wrote extracted text to output.txt
wrote 1142 links to output.links.txt
```

默认会同时生成：

```text
output.pdf
output.txt
output.links.txt
```

如果只想输出 PDF，不提取文本：

```powershell
python .\pdfjm_decrypt.py --netlog .\netlog.json -o .\output.pdf --no-text
```

如果想指定文本输出路径：

```powershell
python .\pdfjm_decrypt.py --netlog .\netlog.json -o .\output.pdf --text-output .\pdf_text.txt
```

如果只想跳过链接提取：

```powershell
python .\pdfjm_decrypt.py --netlog .\netlog.json -o .\output.pdf --no-links
```

如果想指定链接输出路径：

```powershell
python .\pdfjm_decrypt.py --netlog .\netlog.json -o .\output.pdf --links-output .\links.txt
```

## 备用流程：手动提供 decode key

如果你已经从授权后的请求中拿到了 `/api/decodeKey` 返回的 `decrypted_data`，也可以跳过 netlog 自动解析。

使用 CDN URL：

```powershell
python .\pdfjm_decrypt.py `
  -u "https://cdn.pdfjm.com/20260514/file/1778771232156_ef51365d.pdf" `
  -o .\output.pdf
```

脚本会提示输入：

```text
decode key (decrypted_data):
```

也可以把 key 放入本地文本文件：

```powershell
python .\pdfjm_decrypt.py `
  -u "https://cdn.pdfjm.com/20260514/file/1778771232156_ef51365d.pdf" `
  -o .\output.pdf `
  --decode-key-file .\decode_key.txt
```

如果已经有本地加密容器文件：

```powershell
python .\pdfjm_decrypt.py -i .\encrypted.pdf -o .\output.pdf
```

## 可选流程：Playwright 浏览器模式

脚本保留了 Playwright 模式：

```powershell
python .\pdfjm_decrypt.py `
  --share-url "https://pdfjm.cn/#/file/viewer/NTU5MzU3" `
  -o .\output.pdf `
  --wait-for-close
```

理论流程：

```text
1. 脚本打开 Chromium
2. 用户手动扫码
3. 脚本监听 fileInfo、decodeKey、CDN PDF 请求
4. 捕获完成后解密并输出 PDF 和文本
```

实际使用中，网站可能检测 Playwright/自动化浏览器并跳回官网。因此当前更推荐使用真实 Chrome 的 `net-export` 模式。

## 脚本会自动提取什么

`--netlog` 模式会从 `netlog.json` 中自动查找：

```text
/api/decodeKey 返回的 decrypted_data
https://cdn.pdfjm.com/...pdf 加密容器地址
```

然后自动执行：

```text
1. 使用带 Origin/Referer 的请求头下载 CDN 加密容器
2. 解析 pdfjm 加密容器结构
3. 使用 PBKDF2 派生 AES-256-GCM 密钥
4. 分块解密为明文 PDF
5. 使用 pypdf 提取文本到 .txt
6. 提取 PDF 注释链接、显示文字和正文 URL 到 .links.txt
```

这不是手动点击 PDF 里的链接，也不需要逐个整理文档内容。只要 PDF 里有可提取文本，脚本会自动输出到文本文件。

链接输出是 TSV 表格，可以直接用 Excel、WPS、Python、数据库等继续加工。格式为：

```text
page    source        label       url
1       annotation    专属售后群  https://example.com/path
2       text          https://... https://...
```

其中：

```text
page        页码
source      链接来源
label       PDF 页面上显示的链接文字或说明
url         真实链接地址
annotation  PDF 内真实可点击链接，通常能提取 label
text        从页面文本中识别出的 URL，label 通常等于 url
```

注意：如果 PDF 页面是扫描图片，`pypdf` 可能提取不到文本；这种情况需要 OCR，不属于当前脚本范围。

## 已确认的请求链路

首次打开分享页后，前端会请求文件信息：

```text
GET https://pdfjm.cn/go-api/fileInfo?form=h5&fileId=...&scene=&visitor_id=...
```

需要微信授权时，会出现：

```text
GET  https://pdfjm.cn/api/wx/getQrcode?fileId=...&environment=other
POST https://pdfjm.cn/api/wx/checkStatus
```

扫码成功并进入 PDF Viewer 后，关键请求包括：

```text
GET  https://pdfjm.cn/pdfjs-dist/web/viewer.html
POST https://pdfjm.cn/api/visitor/startVisit
POST https://pdfjm.cn/api/decodeKey
GET  https://cdn.pdfjm.com/...pdf
POST https://pdfjm.cn/go-api/visitor/updateSession
```

其中：

```text
/api/decodeKey       返回真正的解密口令 decrypted_data
cdn.pdfjm.com/...pdf 返回加密容器，不是明文 PDF
```

## 加密容器格式

CDN 上的 `.pdf` 文件虽然响应类型是 PDF，但内容实际是加密容器。

容器格式：

```text
前 16 字节: salt
接下来 4 字节: chunk 数量，little-endian
接下来 chunk_count * 12 字节: 每个 chunk 的 AES-GCM IV
接下来 chunk_count * 4 字节: 每个 chunk 的密文长度，little-endian
剩余部分: 分块密文
```

密钥派生：

```text
PBKDF2
hash: SHA-256
iterations: 100000
key length: 256 bit
salt: 文件前 16 字节
password: /api/decodeKey 返回的 decrypted_data
```

解密算法：

```text
AES-GCM-256
IV: 每个 chunk 独立 12 字节 IV
tagLength: 128
```

## 常见问题

### netlog did not contain decrypted_data response body

原因通常是 `chrome://net-export/` 使用了默认记录模式，没有包含响应体。

错误示例：

```text
netlog did not contain decrypted_data response body (logCaptureMode=Default; /api/decodeKey request was present; /api/decodeKey returned 200)
```

解决：

```text
重新导出 netlog，并选择 Include raw bytes。
```

### 403 Client Error: Forbidden for CDN URL

CDN 有请求头校验。脚本已内置 `Origin: https://pdfjm.cn` 和 `Referer: https://pdfjm.cn/` 等请求头。

如果仍然出现 403：

```text
1. 确认 netlog 是授权成功后导出的
2. 确认分享页当时已经正常加载 PDF Viewer
3. 重新抓取 netlog
```

### failed to decrypt chunk

一般表示 `decrypted_data` 和 CDN 文件不匹配，或抓到了旧会话/旧文件的数据。

解决：

```text
重新从打开分享页开始抓包，扫码成功后立刻停止并导出 netlog。
```

### output.txt 为空或内容很少

说明 PDF 可能是扫描图片或文字被转成图片。

解决方向：

```text
需要 OCR 识别，例如 PaddleOCR、Tesseract 或其他 OCR 服务。
```

### output.links.txt 为空

可能原因：

```text
1. PDF 中没有真实链接注释
2. 页面文本里没有完整 URL
3. PDF 是扫描图片，链接只是图片内容
```

如果链接是图片中的文字，也需要 OCR 才能识别。

## 安全与隐私注意事项

1. 只处理你有权限访问的分享文件。
2. 不要尝试绕过微信授权、白名单或访问控制。
3. `netlog.json` 可能包含 Cookie、token、session、访问历史等敏感信息，不要直接分享。
4. 分享日志前必须脱敏，或只截取必要片段。
5. 输出的 PDF 和文本同样可能包含敏感内容，应按原文件权限管理。

