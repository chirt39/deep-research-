<script setup lang="ts">
import { nextTick, ref } from 'vue'

type StreamEvent = {
  type: 'status' | 'phase' | 'route' | 'final' | 'error'
  message?: string
  final?: string
  node?: string
}

type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'status'
  content: string
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

const markdownToHtml = (markdown: string): string => {
  const codeBlocks: string[] = []
  let text = markdown.replace(/```([\s\S]*?)```/g, (_, block) => {
    const index = codeBlocks.length
    codeBlocks.push(`<pre><code>${escapeHtml(String(block).trim())}</code></pre>`)
    return `@@CODE_BLOCK_${index}@@`
  })
  const lines = text.split('\n')
  const out: string[] = []
  let inList = false
  const closeList = () => {
    if (inList) {
      out.push('</ul>')
      inList = false
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
    if (line.startsWith('- ') || line.startsWith('* ')) {
      if (!inList) {
        out.push('<ul>')
        inList = true
      }
      out.push(`<li>${escapeHtml(line.slice(2))}</li>`)
      continue
    }
    closeList()
    out.push(`<p>${escapeHtml(line)}</p>`)
  }
  closeList()
  let html = out.join('')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\[([^[\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
  html = html.replace(/@@CODE_BLOCK_(\d+)@@/g, (_, idx) => codeBlocks[Number(idx)] || '')
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
          messages.value = messages.value.filter((item) => item.id !== statusId)
          messages.value.push({
            id: `a-${Date.now()}`,
            role: 'assistant',
            content: event.final || '已完成，但未返回正文。',
          })
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
            <div class=”guide-grid”>
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
        </div>
      </div>
      <div class="composer">
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
