<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'

type StreamEvent = {
  type: 'status' | 'phase' | 'route' | 'final' | 'error'
  message?: string
  final?: string
  node?: string
  usage?: {
    calls?: number
    cost_yuan?: number
    input_tokens?: number
    output_tokens?: number
  }
  quality?: {
    score?: number
  }
  report_id?: string
  research_domain?: string
  evidence_summary?: {
    evidence_count?: number
    source_count?: number
    source_types?: string[]
    avg_reliability?: number | null
  }
  trace?: string[]
}

type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'status'
  content: string
}

type HistoryItem = {
  id: string
  query: string
  thread_id: string
  user_id: string
  created_at: string
  usage?: {
    calls?: number
    cost_yuan?: number
  }
  quality?: {
    score?: number
  }
}

const userId = ref('user01')
const threadId = ref('thread01')
const tenantId = ref('default_tenant')
const query = ref('')
const loading = ref(false)
const errorMessage = ref('')
const messageListRef = ref<HTMLElement | null>(null)
const composerRef = ref<HTMLTextAreaElement | null>(null)
const progressLogs = ref<string[]>([])
const researchDomain = ref<'auto' | 'general' | 'finance'>('auto')
const lastRunMeta = ref<{
  calls: number
  cost_yuan: number
  quality?: number
  report_id?: string
  research_domain?: string
  evidence_count?: number
  source_count?: number
  trace?: string[]
} | null>(null)
const history = ref<HistoryItem[]>([])
const starterPrompts = [
  {
    title: '个股深度研究',
    prompt:
      '请深度研究比亚迪（002594），包括行业竞争格局、近三年财务健康度、当前估值水平（PE/PB vs 同业）、机构评级变化和主要风险因素，输出完整的投资研报。',
  },
  {
    title: '行业赛道分析',
    prompt:
      '请分析2026年新能源汽车行业的投资机会：市场规模与增速、产业链利润分布、主要玩家竞争壁垒、政策催化方向，以及推荐关注的标的。',
  },
  {
    title: '宏观策略研判',
    prompt:
      '当前国内货币政策处于什么周期？结合CPI/PMI/M2/社融数据，分析对A股市场整体估值的影响，并给出下半年大类资产配置建议。',
  },
  {
    title: '估值对比分析',
    prompt:
      '请对比宁德时代和比亚迪的估值水平：PE/PB/PS/PEG 横向对比 vs 近3年历史分位，DCF 核心假设差异，并给出哪个当前更具性价比的结论。',
  },
]
const capabilityHighlights = [
  {
    title: '五维分析框架',
    desc: '宏观→行业→公司→估值→舆情，五层递进，每个结论绑定可追溯来源。',
  },
  {
    title: '金融信源分层',
    desc: '官方公告>持牌机构研报>头部财经媒体>数据平台>自媒体，自动打分去重。',
  },
  {
    title: '多维估值模型',
    desc: '相对估值（PE/PB/PS/PEG）+ 绝对估值（DCF），同业对比与历史分位交叉验证。',
  },
]
const landingMetrics = [
  { label: '分析维度', value: '宏观·行业·公司·估值·舆情' },
  { label: '证据来源', value: 'Web + 金融API + 知识库' },
  { label: '输出标准', value: '专业投研报告' },
]
const messages = ref<ChatMessage[]>([
  {
    id: `m-${Date.now()}`,
    role: 'assistant',
      content: '你好，我是 DeepResearch 金融投研助手。输入股票代码或研究问题，我会自动执行宏观研判→行业分析→公司深度→估值模型→舆情跟踪的全链路分析，输出专业投研报告。',
  },
])

const escapeHtml = (value: string): string =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

const renderTable = (rows: string[]): string => {
  const cells = (row: string) => row.split('|').slice(1, -1).map((c) => c.trim())
  const headerRow = rows[0] ?? ''
  const head = cells(headerRow).map((c) => `<th>${escapeHtml(c)}</th>`).join('')
  const body = rows
    .slice(2)
    .map((row) => `<tr>${cells(row).map((c) => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`)
    .join('')
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`
}

const markdownToHtml = (markdown: string): string => {
  const codeBlocks: string[] = []
  let text = markdown.replace(/```([\s\S]*?)```/g, (_, block) => {
    const index = codeBlocks.length
    codeBlocks.push(`<pre><code>${escapeHtml(String(block).trim())}</code></pre>`)
    return `@@CODE_BLOCK_${index}@@`
  })
  const tableBlocks: string[] = []
  text = text.replace(/((?:^\|.*\n?)+)/gm, (block) => {
    const rows = block.split('\n').map((r) => r.trim()).filter((r) => r.startsWith('|'))
    const separatorRow = rows[1] ?? ''
    if (rows.length < 2 || !/^\|?[\s:\-|]+\|?$/.test(separatorRow)) return block
    const index = tableBlocks.length
    tableBlocks.push(renderTable(rows))
    return `@@TABLE_${index}@@`
  })
  const lines = text.split('\n')
  const out: string[] = []
  let inList = false
  let listType = ''
  const closeList = () => {
    if (inList) {
      out.push(`</${listType}>`)
      inList = false
      listType = ''
    }
  }
  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      closeList()
      continue
    }
    if (line.startsWith('# ')) {
      closeList()
      out.push(`<h1>${escapeHtml(line.slice(2))}</h1>`)
      continue
    }
    if (line.startsWith('## ')) {
      closeList()
      out.push(`<h2>${escapeHtml(line.slice(3))}</h2>`)
      continue
    }
    if (line.startsWith('### ')) {
      closeList()
      out.push(`<h3>${escapeHtml(line.slice(4))}</h3>`)
      continue
    }
    const orderedMatch = line.match(/^(\d+)\.\s+(.*)$/)
    if (orderedMatch) {
      if (listType !== 'ol') {
        closeList()
        out.push('<ol>')
        inList = true
        listType = 'ol'
      }
      out.push(`<li>${escapeHtml(orderedMatch[2] ?? '')}</li>`)
      continue
    }
    if (line.startsWith('- ') || line.startsWith('* ')) {
      if (listType !== 'ul') {
        closeList()
        out.push('<ul>')
        inList = true
        listType = 'ul'
      }
      out.push(`<li>${escapeHtml(line.slice(2))}</li>`)
      continue
    }
    closeList()
    if (line.startsWith('> ')) {
      out.push(`<blockquote>${escapeHtml(line.slice(2))}</blockquote>`)
      continue
    }
    if (/^(-{3,}|\*{3,})$/.test(line)) {
      out.push('<hr />')
      continue
    }
    out.push(`<p>${escapeHtml(line)}</p>`)
  }
  closeList()
  let html = out.join('')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\[([^[\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
  html = html.replace(/@@CODE_BLOCK_(\d+)@@/g, (_, idx) => codeBlocks[Number(idx)] || '')
  html = html.replace(/@@TABLE_(\d+)@@/g, (_, idx) => tableBlocks[Number(idx)] || '')
  return html
}

const renderMessageHtml = (message: ChatMessage) => markdownToHtml(message.content || '')

const scrollToBottom = async () => {
  await nextTick()
  const el = messageListRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

const createNewChat = () => {
  messages.value = [
    {
      id: `m-${Date.now()}`,
      role: 'assistant',
      content: '已开始新会话。输入股票代码或研究问题即可开始分析。',
    },
  ]
  progressLogs.value = []
  lastRunMeta.value = null
  errorMessage.value = ''
  query.value = ''
}

const usePrompt = async (prompt: string) => {
  query.value = prompt
  errorMessage.value = ''
  await nextTick()
  composerRef.value?.focus()
}

const applyStarterByIndex = (index: number) => {
  const target = starterPrompts[index]
  if (!target) return
  usePrompt(target.prompt)
}

const pushProgress = (message: string) => {
  const msg = message.trim()
  if (!msg) return
  const last = progressLogs.value[progressLogs.value.length - 1]
  if (last === msg) return
  progressLogs.value.push(msg)
  if (progressLogs.value.length > 6) {
    progressLogs.value = progressLogs.value.slice(-6)
  }
}

const runResearch = async () => {
  const userText = query.value.trim()
  if (!userText || loading.value) return
  loading.value = true
  errorMessage.value = ''
  progressLogs.value = []
  lastRunMeta.value = null
  query.value = ''
  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content: userText })
  const statusId = `s-${Date.now()}`
  messages.value.push({ id: statusId, role: 'status', content: '正在初始化执行链路...' })
  const renderStatusText = () => {
    const statusMessage = messages.value.find((item) => item.id === statusId)
    if (!statusMessage) return
    const latest = progressLogs.value.slice(-8)
    statusMessage.content = ['正在处理中...', ...latest].map((line) => `- ${line}`).join('\n')
  }
  renderStatusText()
  await scrollToBottom()
  try {
    const response = await fetch('/api/v1/research/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: userText,
        user_id: userId.value.trim() || 'default_user',
        thread_id: threadId.value.trim() || 'default_thread',
        tenant_id: tenantId.value.trim() || 'default_tenant',
        research_domain: researchDomain.value,
      }),
    })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || `请求失败: ${response.status}`)
    }
    if (!response.body) {
      throw new Error('流式响应不可用')
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        const jsonText = part.slice(6).trim()
        if (!jsonText) continue
        const event = JSON.parse(jsonText) as StreamEvent
        if (event.type === 'status' || event.type === 'phase' || event.type === 'route') {
          const prefix = event.type === 'phase' && event.node ? `[${event.node}] ` : ''
          pushProgress(`${prefix}${event.message || ''}`)
          renderStatusText()
        }
        if (event.type === 'final') {
          lastRunMeta.value = {
            calls: event.usage?.calls ?? 0,
            cost_yuan: event.usage?.cost_yuan ?? 0,
            quality: event.quality?.score,
            report_id: event.report_id,
            research_domain: event.research_domain,
            evidence_count: event.evidence_summary?.evidence_count,
            source_count: event.evidence_summary?.source_count,
            trace: event.trace,
          }
          messages.value = messages.value.filter((item) => item.id !== statusId)
          messages.value.push({
            id: `a-${Date.now()}`,
            role: 'assistant',
            content: event.final || '已完成，但未返回正文。',
          })
          loadHistory()
        }
        if (event.type === 'error') {
          throw new Error(event.message || '服务端执行异常')
        }
      }
      await scrollToBottom()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '请求失败'
    messages.value = messages.value.filter((item) => item.id !== statusId)
    messages.value.push({
      id: `e-${Date.now()}`,
      role: 'assistant',
      content: `请求失败：${errorMessage.value}`,
    })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

const copyMessage = async (message: ChatMessage) => {
  const text = message.content || ''
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
}

const downloadMessage = (message: ChatMessage) => {
  const blob = new Blob([message.content || ''], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `deepresearch-report-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.md`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const formatTime = (iso: string) => {
  if (!iso) return ''
  const d = new Date(iso)
  const month = d.getMonth() + 1
  const day = d.getDate()
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${month}/${day} ${hour}:${minute}`
}

const loadHistory = async () => {
  try {
    const response = await fetch('/api/v1/research/history?limit=20')
    if (!response.ok) return
    const data = await response.json()
    history.value = data.reports || []
  } catch {
    // 历史列表加载失败不影响主流程
  }
}

const viewHistory = async (item: HistoryItem) => {
  try {
    const response = await fetch(`/api/v1/research/history/${item.id}`)
    if (!response.ok) return
    const report = await response.json()
    lastRunMeta.value = {
      calls: report.usage?.calls ?? 0,
      cost_yuan: report.usage?.cost_yuan ?? 0,
      quality: report.quality?.score,
      report_id: report.id,
      research_domain: report.research_domain,
      evidence_count: report.evidence_summary?.evidence_count,
      source_count: report.evidence_summary?.source_count,
      trace: report.trace,
    }
    messages.value = [
      { id: `h-${Date.now()}`, role: 'user', content: report.query || '历史报告' },
      { id: `a-${Date.now()}`, role: 'assistant', content: report.final || '' },
    ]
    errorMessage.value = ''
    await scrollToBottom()
  } catch {
    errorMessage.value = '历史报告加载失败'
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<template>
  <div class="chat-shell">
    <aside class="chat-sidebar">
      <div class="sidebar-brand">
        <p class="brand-badge">FinResearch</p>
        <h1>DeepResearch</h1>
        <p class="brand-desc">金融多智能体深度投研平台，覆盖宏观·行业·公司·估值·舆情五维分析。</p>
      </div>
      <div class="sidebar-head">
        <button class="new-chat-btn" @click="createNewChat">新建会话</button>
      </div>
      <div class="quick-entry">
        <p class="section-title">推荐起手问题</p>
        <button
          v-for="item in starterPrompts.slice(0, 3)"
          :key="item.title"
          class="quick-entry-btn"
          @click="usePrompt(item.prompt)"
        >
          {{ item.title }}
        </button>
      </div>
      <div class="settings-group">
        <label>User ID</label>
        <input v-model="userId" class="sidebar-input" />
      </div>
      <div class="settings-group">
        <label>Thread ID</label>
        <input v-model="threadId" class="sidebar-input" />
      </div>
      <div class="settings-group">
        <label>Tenant ID</label>
        <input v-model="tenantId" class="sidebar-input" />
      </div>
      <p class="hint-text">当前会话记忆键：{{ userId }} / {{ threadId }}</p>
      <div class="history-group">
        <p class="section-title">历史报告</p>
        <div v-if="history.length === 0" class="history-empty">暂无历史报告</div>
        <button
          v-for="item in history.slice(0, 10)"
          :key="item.id"
          class="history-item"
          :title="item.query"
          @click="viewHistory(item)"
        >
          <span class="history-query">{{ item.query }}</span>
          <span class="history-time">{{ formatTime(item.created_at) }}</span>
        </button>
      </div>
    </aside>

    <main class="chat-main">
      <header class="main-header">
        <div>
          <h2>DeepResearch 金融投研工作台</h2>
          <p>面向投资研究团队的专业级智能分析平台，从问题定义到专业研报输出的全链路自动化。</p>
        </div>
        <div class="header-tags">
          <span>五维分析框架</span>
          <span>信源交叉验证</span>
          <span>券商级研报</span>
        </div>
      </header>
      <div ref="messageListRef" class="message-list">
        <section v-if="messages.length <= 1" class="onboarding-panel">
          <div class="hero-panel">
            <p class="hero-badge">宏观研判 · 行业分析 · 公司深度 · 估值模型 · 舆情跟踪</p>
            <h3>输入股票代码或研究问题，自动生成专业投研报告</h3>
            <p class="hero-desc">
              推荐提问结构：标的 + 分析维度 + 时间范围。系统自动执行宏观/行业/公司/估值/舆情五维分析。
            </p>
            <div class="hero-actions">
              <button class="hero-btn primary" @click="applyStarterByIndex(0)">个股深度研究</button>
              <button class="hero-btn" @click="applyStarterByIndex(1)">行业赛道分析</button>
            </div>
            <div class="metric-grid">
              <article v-for="item in landingMetrics" :key="item.label">
                <p>{{ item.label }}</p>
                <strong>{{ item.value }}</strong>
              </article>
            </div>
          </div>
          <div class="capability-grid">
            <article v-for="item in capabilityHighlights" :key="item.title" class="capability-card">
              <h4>{{ item.title }}</h4>
              <p>{{ item.desc }}</p>
            </article>
          </div>
          <div class="guide-panel">
            <h4>提问指南</h4>
            <div class="guide-grid">
              <article>
                <h5>1. 指定标的</h5>
                <p>输入股票代码或公司名称，例如「002594 比亚迪」或「宁德时代」。</p>
              </article>
              <article>
                <h5>2. 明确维度</h5>
                <p>选择关注的分析维度：财务健康度 / 估值水平 / 行业竞争 / 宏观影响 / 机构评级。</p>
              </article>
              <article>
                <h5>3. 限定范围</h5>
                <p>给出时间跨度和比较基准，例如「近三年财务数据」「与宁德时代对比」。</p>
              </article>
            </div>
          </div>
          <div class="prompt-list">
            <button v-for="item in starterPrompts" :key="item.prompt" class="prompt-chip" @click="usePrompt(item.prompt)">
              {{ item.prompt }}
            </button>
          </div>
        </section>
        <div
          v-for="message in messages"
          :key="message.id"
          class="message-row"
          :class="`role-${message.role}`"
        >
          <div class="avatar">{{ message.role === 'user' ? '你' : message.role === 'status' ? '...' : 'AI' }}</div>
          <div class="bubble markdown-body" v-html="renderMessageHtml(message)"></div>
          <button
            v-if="message.role === 'assistant'"
            class="copy-btn"
            title="复制报告 Markdown"
            @click="copyMessage(message)"
          >
            复制
          </button>
          <button
            v-if="message.role === 'assistant'"
            class="copy-btn"
            title="下载报告 Markdown"
            @click="downloadMessage(message)"
          >
            下载
          </button>
        </div>
      </div>
      <p v-if="lastRunMeta" class="run-meta">
        本次研究：{{ lastRunMeta.calls }} 次 LLM 调用，约 ¥{{ lastRunMeta.cost_yuan.toFixed(4) }}
        <template v-if="lastRunMeta.quality !== undefined"> ｜ 质量自检 {{ lastRunMeta.quality }}/100</template>
        <template v-if="lastRunMeta.research_domain"> ｜ 研究域 {{ lastRunMeta.research_domain }}</template>
        <template v-if="lastRunMeta.evidence_count !== undefined"> ｜ 证据 {{ lastRunMeta.evidence_count }} 条</template>
      </p>
      <div class="composer">
        <select v-model="researchDomain" class="domain-select" :disabled="loading" title="选择研究域">
          <option value="auto">自动识别</option>
          <option value="general">企业/技术研究</option>
          <option value="finance">金融投研</option>
        </select>
        <textarea
          v-model="query"
          ref="composerRef"
          class="composer-input"
          :disabled="loading"
          placeholder="输入你的问题，回车发送（Shift + Enter 换行）"
          @keydown.enter.exact.prevent="runResearch"
        />
        <button class="send-btn" :disabled="loading || !query.trim()" @click="runResearch">
          {{ loading ? '处理中...' : '发送' }}
        </button>
      </div>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </main>
  </div>
</template>
