<template>
  <section class="page" data-module="aeration">
    <header class="page-head">
      <div>
        <h2>曝气控制管理</h2>
        <p class="page-desc">维护曝气记录，围绕记录编号、曝气池编号、溶解氧值、风量设定做登记、筛选与状态流转。参数锁定后只读，跨值班记录按归属区分操作权限。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记曝气记录</button>
        <button class="btn" type="button" @click="exportRows">导出曝气控制清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>控制状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <input
              v-if="column === '溶解氧值' && canEdit(row)"
              v-model="drafts[String(row.id)].doValue"
              class="cell-input"
              type="number"
              step="0.1"
              aria-label="溶解氧值"
            />
            <input
              v-else-if="column === '风量设定' && canEdit(row)"
              v-model="drafts[String(row.id)].airFlow"
              class="cell-input"
              type="number"
              step="10"
              aria-label="风量设定"
            />
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <template v-if="nextAction(row.status)">
              <button
                class="link"
                type="button"
                :disabled="!canOperate(row)"
                :title="actionTitle(row)"
                @click="runAction(nextAction(row.status), row)"
              >
                {{ nextAction(row.status) }}
              </button>
            </template>
            <span v-else class="action-note">
              {{ row.status === '已锁定' ? '参数已锁定·只读' : '—' }}
            </span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条曝气控制记录，当前值班人：{{ session.operator }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

interface Row {
  id: number | string
  status: string
  [field: string]: string | number | null
}

interface Draft {
  doValue: string
  airFlow: string
}

const ENDPOINT = '/api/aeration'
const columns = ["记录编号", "曝气池编号", "溶解氧值", "风量设定", "风机频率", "调节时间", "操作人员", "控制状态"]
const statuses = ["待调节", "已调节", "待复核", "已锁定"]
// 与后端状态机保持一致：每个状态只对应一个合法后继动作，已锁定没有后继。
const NEXT_ACTION: Record<string, string> = {
  '待调节': '提交调节',
  '已调节': '复核确认',
  '待复核': '锁定参数',
}

const session = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const drafts = ref<Record<string, Draft>>({})

const lockedCount = computed(() => rows.value.filter((row) => row.status === '已锁定').length)
const stats = computed(() => [
  { label: '本页调节次数', value: rows.value.filter((row) => ['已调节', '待复核', '已锁定'].includes(String(row.status))).length },
  { label: '溶解氧均值', value: averageDo() },
  { label: '锁定参数项', value: lockedCount.value },
])
const hasFilter = computed(() => keyword.value.trim() !== '' || statusFilter.value !== '')
const emptyText = computed(() =>
  hasFilter.value ? '没有符合筛选条件的曝气记录，请调整查询条件或重置条件' : '暂无曝气控制数据，可先登记曝气记录',
)

function averageDo(): string {
  const values = rows.value
    .map((row) => Number(row['溶解氧值']))
    .filter((value) => Number.isFinite(value))
  if (!values.length) {
    return '—'
  }
  return (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2)
}

function isOwned(row: Row): boolean {
  return String(row['操作人员'] ?? '') === session.operator
}

function canEdit(row: Row): boolean {
  // 只有归属本人、且处于待调节状态的记录才能改溶解氧与风量；锁定后一律只读。
  return row.status === '待调节' && isOwned(row)
}

function canOperate(row: Row): boolean {
  return nextAction(row.status) !== '' && isOwned(row)
}

function nextAction(status: string): string {
  return NEXT_ACTION[status] ?? ''
}

function actionTitle(row: Row): string {
  if (!isOwned(row)) {
    return `该记录归属「${String(row['操作人员'] ?? '未知')}」，当前值班人无权操作`
  }
  return ''
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = ''
  successMessage.value = '曝气记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  const draft = drafts.value[row.id]
  const body: Record<string, string> = {
    action,
    '操作人员': session.operator,
  }
  if (action === '提交调节') {
    body['溶解氧值'] = draft?.doValue ?? ''
    body['风量设定'] = draft?.airFlow ?? ''
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload) {
      throw new Error('曝气控制动作未生效，请稍后重试')
    }
    if (!payload.ok) {
      // 锁定拦截、重复调节、空数据、越权等说明以后端返回为准。
      errorMessage.value = payload.message || '曝气控制动作未生效'
      return
    }
    successMessage.value = payload.message || '曝气控制操作成功'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '曝气控制操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  successMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) {
    params.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  const query = params.toString()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error('曝气记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 列表与详情共用同一份后端口径，刷新后仍可编辑待调节参数。
    drafts.value = {}
    for (const row of rows.value) {
      drafts.value[String(row.id)] = {
        doValue: String(row['溶解氧值'] ?? ''),
        airFlow: String(row['风量设定'] ?? ''),
      }
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '曝气控制列表读取失败'
  }
}

onMounted(reload)
</script>
