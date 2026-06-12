import {
  ArrowUpRight,
  Copy,
  Database,
  Filter,
  Link as LinkIcon,
  MessageCircle,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import * as React from 'react';
import linksData from './data/links.json';
import statsData from './data/stats.json';

type ResourceLink = {
  id: string;
  title: string;
  url: string;
  domain: string;
  category: string;
  tags: string[];
  score: number;
  page: number;
  status: string;
  notes: string[];
};

type SiteStats = {
  publicCount: number;
  totalCleanCount: number;
  paidPreviewCount: number;
  reviewCount: number;
  categories: Record<string, number>;
  publicCategories: Record<string, number>;
  topDomains: Record<string, number>;
  contactSlots: {
    wechatQr: string;
    wechatGroupImage: string;
    telegram: string;
    email: string;
  };
};

const links = linksData as ResourceLink[];
const stats = statsData as SiteStats;

const categoryOrder = [
  '全部',
  '搜索源',
  '软件工具',
  'AI工具',
  '设计素材',
  '学习资料',
  '教程文章',
  '未分类',
];

function normalize(value: string) {
  return value.toLowerCase().trim();
}

function copyLink(url: string) {
  void navigator.clipboard.writeText(url);
}

export function App() {
  const [query, setQuery] = React.useState('');
  const [category, setCategory] = React.useState('全部');

  const categories = React.useMemo(() => {
    const values = new Set(links.map((link) => link.category));
    const ordered = categoryOrder.filter((item) => item === '全部' || values.has(item));
    const rest = Array.from(values)
      .filter((item) => !ordered.includes(item))
      .sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'));
    return [...ordered, ...rest];
  }, []);

  const filtered = React.useMemo(() => {
    const text = normalize(query);
    return links
      .filter((link) => category === '全部' || link.category === category)
      .filter((link) => {
        if (!text) return true;
        return normalize(`${link.title} ${link.domain} ${link.url} ${link.tags.join(' ')}`).includes(text);
      })
      .sort((a, b) => b.score - a.score || a.page - b.page || a.title.localeCompare(b.title, 'zh-Hans-CN'));
  }, [category, query]);

  return (
    <main className="app-shell">
      <section className="topbar">
        <div className="brand">
          <p className="eyebrow">Resource Index</p>
          <h1>elton 的资源索引库</h1>
        </div>
        <div className="top-actions">
          <a className="ghost-button" href="#contact">
            完整版入口
          </a>
        </div>
      </section>

      <section className="workspace">
        <aside className="sidebar">
          <div className="search-box">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索标题、域名、标签或 URL"
            />
          </div>

          <details className="summary-panel" open>
            <summary>
              <Database size={16} />
              数据概览
            </summary>
            <div className="metric-grid">
              <Metric icon={<LinkIcon size={18} />} label="公开资源" value={stats.publicCount} />
              <Metric icon={<Database size={18} />} label="完整库" value={stats.totalCleanCount} />
              <Metric icon={<ShieldCheck size={18} />} label="付费预览" value={stats.paidPreviewCount} />
              <Metric icon={<Sparkles size={18} />} label="待复核" value={stats.reviewCount} />
            </div>
          </details>

          <FilterGroup
            icon={<Filter size={16} />}
            title="分类"
            values={categories}
            selected={category}
            counts={{ 全部: links.length, ...stats.publicCategories }}
            onSelect={setCategory}
          />

          <details id="contact" className="contact-panel">
            <summary className="section-title">
              <MessageCircle size={16} />
              完整版与社群
            </summary>
            <p>
              当前页面展示公开精选资源。完整版保留网盘、站内资源、超时待复核项和更多未公开链接，可接入微信二维码、群聊图片或 TG 入口。
            </p>
            <div className="contact-slots">
              <span>微信二维码：待配置</span>
              <span>群聊图片：待配置</span>
              <span>TG 群：待配置</span>
            </div>
          </details>
        </aside>

        <section className="content">
          <div className="results-bar">
            <div>
              <h2>{category === '全部' ? '全部公开资源' : category}</h2>
              <p>
                当前显示 {filtered.length} 条；分类数字只统计公开版数据。未分类资源保留为独立模块，后续可人工整理。
              </p>
            </div>
          </div>

          <div className="resource-grid">
            {filtered.map((link) => (
              <ResourceCard key={link.id} link={link} />
            ))}
          </div>

          {filtered.length === 0 && (
            <div className="empty-state">
              <Search size={28} />
              <h3>没有匹配结果</h3>
              <p>换一个关键词，或清空分类和标签筛选。</p>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FilterGroup({
  icon,
  title,
  values,
  selected,
  counts,
  onSelect,
}: {
  icon: React.ReactNode;
  title: string;
  values: string[];
  selected: string;
  counts: Record<string, number>;
  onSelect: (value: string) => void;
}) {
  return (
    <section className="filter-group">
      <div className="section-title">
        {icon}
        <h2>{title}</h2>
      </div>
      <div className="filter-list">
        {values.map((value) => (
          <button
            key={value}
            className={selected === value ? 'active' : ''}
            onClick={() => onSelect(value)}
            type="button"
          >
            <span>{value}</span>
            {counts[value] !== undefined && <em>{counts[value]}</em>}
          </button>
        ))}
      </div>
    </section>
  );
}

function ResourceCard({ link }: { link: ResourceLink }) {
  return (
    <article className="resource-card">
      <div className="card-main">
        <div className="card-heading">
          <h3>{link.title}</h3>
        </div>
        <a href={link.url} target="_blank" rel="noreferrer" className="domain">
          {link.domain}
        </a>
        <div className="tag-row">
          <span>{link.category}</span>
          {link.tags.slice(0, 3).map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </div>
      <div className="card-footer">
        <small>{link.category}</small>
        <div className="card-actions">
          <button type="button" title="复制链接" onClick={() => copyLink(link.url)}>
            <Copy size={16} />
          </button>
          <a href={link.url} target="_blank" rel="noreferrer" title="打开链接">
            <ArrowUpRight size={17} />
          </a>
        </div>
      </div>
    </article>
  );
}
