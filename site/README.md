# 资源索引静态站

这是从 `output.links.txt` 清洗后的公开资源导航站。当前采用全量公开静态试水模式：除前创作者相关页面、运营页、反馈页、协议页等已剔除内容外，其余清洗后的链接都会打包进静态站。

## 数据来源

站点数据由根目录脚本生成：

```powershell
.\.venv\Scripts\python.exe .\tools\clean_links.py --input .\output.links.txt --output-dir .\data
```

生成到：

```text
site/src/data/links.json
site/src/data/stats.json
```

当前策略：

```text
公开数据包含清洗后的全量链接。
前创作者运营页、反馈页、协议页等不会进入站点数据。
当前是全量静态公开模式，因此站点前端会包含这些公开链接。
```

## 本地运行

```powershell
cd .\site
npm install
npm run dev
```

## 生产构建

```powershell
cd .\site
npm run build
```

输出目录：

```text
site/dist
```

## 部署建议

Cloudflare Pages:

```text
Root directory: site
Build command: npm run build
Output directory: dist
```

优先建议 Cloudflare Pages。它适合静态站，自动构建、自动 HTTPS、CDN 分发，并且后续可以自然接 Cloudflare Workers、D1、R2 做会员接口或资源交付。

GitHub Pages 也能托管静态站，但后续如果要接付费会员和后端权限，通常还要额外接其他服务。

### 通过 GitHub 导入 Cloudflare Pages

可以新建 GitHub 仓库，然后在 Cloudflare Pages 里选择“导入现有 Git 存储库”。

建议提交：

```text
site/
tools/
requirements.txt
pdfjm_decrypt.py
pdfjm_capture_readme.md
.gitignore
```

不要提交：

```text
.venv/
site/node_modules/
site/dist/
netlog.json
output.pdf
output.txt
output.links.txt
data/links.full.*
data/links.review.*
```

当前 `.gitignore` 已默认排除这些敏感或可再生成文件。

## 静态数据边界

当前你选择全量静态公开试水，因此 `site/src/data/links.json` 会包含 1000+ 条清洗后的链接。

如果后续切回付费模式，不要把完整版 `data/links.full.json` 直接复制到 `site/src/data` 或 `site/public`。

原因：

```text
静态站里的 JS/JSON/CSS/HTML 都会被浏览器下载。
只要数据被打包进前端，用户就能从浏览器开发者工具或网络请求中拿到。
前端隐藏、混淆、条件渲染都不能保护付费数据。
```

推荐做法：

```text
阶段 1:
静态站只放免费数据，完整版通过人工/第三方平台交付。

阶段 2:
用小报童、知识星球、爱发电、Gumroad、Notion/飞书私有库等承接付费。

阶段 3:
如果收入验证成立，再做后端会员系统。
后端可以选 Cloudflare Workers + D1、Supabase、VPS + 数据库等。
```

当前站点使用：

```text
site/src/data/links.json
site/src/data/stats.json
```

其中 `links.json` 是当前公开数据，`stats.json` 包含统计和入口占位。

## 扩展位

联系和付费入口当前是占位：

```text
微信二维码
群聊图片
TG 群
邮箱
```

后续可以在 `site/src/data/stats.json` 的 `contactSlots` 中写入真实地址，或改为专门的配置文件。
