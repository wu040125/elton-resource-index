# 链接清洗分类输出说明

本目录由 `tools/clean_links.py` 从 `output.links.txt` 生成，只做数据清洗、分类、验证和免费/完整版切分，不构建网站。

## 输出文件

```text
links.full.json     完整版 JSON，后续网站付费/完整数据源
links.full.tsv      完整版表格，方便人工审查
links.free.json     免费版 JSON，后续静态站公开数据源
links.free.tsv      免费版表格，方便人工审查
links.review.json   需要人工复核的数据
links.review.tsv    需要人工复核的表格
summary.json        本次处理统计
```

## 当前结果

```text
总链接行数: 1142
唯一 URL: 1079
免费版: 185
完整版付费/保留: 926
复核清单: 93
```

免费版当前只保留：

```text
HTTP 验证 ok
非 pdfjm.top 站内资源
非网盘直链
非前拥有者运营页/反馈页/协议页
分类适合公开引流
评分达到阈值
```

## 字段说明

```text
id              稳定短 ID
page            原 PDF 页码
source          原始来源，当前主要是 annotation
title           清洗后的标题
original_title  PDF 中提取的原始标题
url             原始 URL
normalized_url  去掉部分追踪参数后的 URL
domain          域名
category        规则分类
tags            标签
score           0-100 质量分
tier            free / paid / review
is_free         是否进入免费版
status          ok / restricted / missing / timeout / error
http_status     HTTP 状态码
final_url       跳转后的最终 URL
notes           处理备注
```

## 分类规则

当前使用规则分类，结合标题、URL、域名关键词判断。

主要分类：

```text
搜索源
AI工具
学习资料
软件工具
设计素材
影音娱乐
网盘资源
文档知识库
教程文章
运营页面
未分类
```

## 评分逻辑

评分不是网站权威评级，只是用于排序和筛选的实用分。

加分项：

```text
URL 当前可访问
HTTPS
标题长度合理
属于搜索源、工具、学习、设计等公开展示价值较高的类别
```

扣分项：

```text
超时、错误、404
HTTP 明文链接
标题过短，例如 “a”“等”
短链
跳转链
pdfjm.top 站内资源
运营页、反馈页、协议页
```

## 免费版策略

免费版用于静态网站引流，不用于暴露全部资源。

当前免费版偏向：

```text
搜索源
公开工具站
AI 工具站
设计素材站
少量学习资料/教程
```

当前免费版排除：

```text
网盘直链
pdfjm.top 站内资源
前拥有者相关 Flowus 页面
售后/反馈/协议/发展历程页面
当前验证不可访问的站点
明显低质量标题
```

## 验证注意事项

URL 验证是轻量 HTTP 检查：

```text
先 HEAD
必要时 GET
单 URL 超时 5 秒
并发 24
```

`timeout` 不一定代表网站失效，可能是网络环境、跨境访问、反爬或站点响应慢。因此完整版保留这些链接，免费版暂不展示。

## 重新生成

```powershell
.\.venv\Scripts\python.exe .\tools\clean_links.py --input .\output.links.txt --output-dir .\data
```

跳过联网验证：

```powershell
.\.venv\Scripts\python.exe .\tools\clean_links.py --input .\output.links.txt --output-dir .\data --no-validate
```

脚本会复用 `data/links.full.json` 中已有 URL 的验证结果，避免每次重复验证全部链接。
