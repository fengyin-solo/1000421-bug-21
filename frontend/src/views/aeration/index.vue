<template>
  <section class="page" data-module="aeration">
    <header class="page-head">
      <div>
        <h2>曝气控制管理</h2>
        <p class="page-desc">维护曝气记录，围绕记录编号、曝气池编号、溶解氧值、风量设定做登记、筛选与状态流转。</p>
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
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(row).length" class="locked-tag">已锁定只读</span>
            <button class="link" type="button" @click="openDetail(row)">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            {{ hasActiveFilter ? '当前筛选条件下没有曝气控制记录，可重置条件后再查' : '暂无曝气控制数据，可先登记曝气记录' }}
          </td>
        </tr>
      </tbody>
    </table>

    <section v-if="selected" class="detail-panel">
      <header class="detail-head">
        <h3>曝气记录详情：{{ selected.记录编号 ?? selected.id }}</h3>
        <span v-if="isLocked" class="locked-tag">已锁定，参数只读</span>
        <button class="btn ghost" type="button" @click="closeDetail">收起</button>
      </header>
      <dl class="detail-grid">
        <div v-for="field in detailFields" :key="field" class="detail-item">
          <dt>{{ field }}</dt>
          <dd>{{ selected[field] ?? '—' }}</dd>
        </div>
        <div v-for="field in editableFields" :key="field" class="detail-item">
          <dt>{{ field }}</dt>
          <dd>
            <input
              v-model="editForm[field]"
              :disabled="isLocked"
              :placeholder="isLocked ? '已锁定，不可修改' : `填写${field}`"
            />
          </dd>
        </div>
      </dl>
      <footer class="detail-foot">
        <button
          v-for="action in availableActions(selected)"
          :key="action"
          class="btn primary"
          type="button"
          @click="runAction(action, selected)"
        >
          {{ action }}
        </button>
        <span v-if="!availableActions(selected).length" class="locked-tag">
          记录已锁定，溶解氧值与风量设定只读，不能再执行任何动作
        </span>
      </footer>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条曝气控制记录</span>
      <span v-if="successMessage" class="success-text">{{ successMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/aeration'
const columns = ["记录编号", "曝气池编号", "溶解氧值", "风量设定", "风机频率", "调节时间", "操作人员", "控制状态"]
const stats = [{"label": "今日调节次数", "value": 0}, {"label": "溶解氧均值", "value": 0}, {"label": "锁定参数项", "value": 0}]
// 锁定后只读的参数，只允许随「提交调节」修改，与后端 EDITABLE_FIELDS 保持一致
const editableFields = ["溶解氧值", "风量设定", "风机频率"]
const detailFields = ["记录编号", "曝气池编号", "调节时间", "操作人员", "锁定人", "控制状态", "status"]
// 各状态允许执行的动作，与后端 ACTION_SOURCES 保持一致；已锁定是终态
const actionsByStatus: Record<string, string[]> = {
  "待调节": ["提交调节"],
  "已调节": ["复核确认"],
  "待复核": ["锁定参数"],
  "已锁定": [],
}

const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const selected = ref<Row | null>(null)
const editForm = ref<Record<string, string>>({})

const hasActiveFilter = computed(() =>
  Object.values(filters.value).some((value) => String(value ?? '').trim()),
)
const isLocked = computed(() => selected.value?.status === '已锁定')

function availableActions(row: Row): string[] {
  return actionsByStatus[String(row.status ?? '')] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '曝气记录登记入口尚未接入审批流'
}

function closeDetail() {
  selected.value = null
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    const detail = await response.json()
    if (!response.ok) {
      throw new Error(detail?.detail ?? '曝气记录详情读取失败')
    }
    selected.value = detail
    editForm.value = Object.fromEntries(
      editableFields.map((field) => [field, String(detail[field] ?? '')]),
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '曝气记录详情读取失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  const body: Record<string, unknown> = { action, 操作人员: session.operator }
  if (action === '提交调节') {
    // 详情面板打开时提交修改后的参数，否则按记录当前参数提交
    const source = selected.value?.id === row.id ? editForm.value : row
    for (const field of editableFields) {
      body[field] = source[field] ?? ''
    }
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message ?? payload?.detail ?? '曝气控制动作未生效，请稍后重试')
    }
    successMessage.value = payload.message ?? `曝气记录已${action}`
    await reload()
    if (selected.value?.id === row.id) {
      await openDetail(row)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '曝气控制操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('曝气记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '曝气控制列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.detail-panel {
  margin-top: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.detail-head h3 {
  margin: 0;
  font-size: 15px;
  flex: 1;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px 16px;
  margin: 12px 0;
}
.detail-item dt {
  font-size: 12px;
  color: var(--muted);
}
.detail-item dd {
  margin: 2px 0 0;
  font-size: 13px;
}
.detail-item input {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.detail-item input:disabled {
  background: #f1f5f9;
  color: var(--muted);
  cursor: not-allowed;
}
.detail-foot {
  display: flex;
  align-items: center;
  gap: 10px;
}
.locked-tag {
  color: #b42318;
  font-size: 12px;
}
.success-text {
  color: #067647;
}
</style>
