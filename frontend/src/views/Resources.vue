<template>
  <div class="resources-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">工具中心</h2>
        <p class="page-desc">发现、注册并试用工具 / Skill / MCP；调用结果与最近记录在试用台查看。</p>
      </div>
      <div class="header-actions">
        <el-button v-if="userStore.hasPermission('resource:invoke')" @click="showBatch = true">冻结批次</el-button>
        <el-button v-if="userStore.hasPermission('resource:invoke')" @click="openMcpWorkbench()">MCP 连接</el-button>
        <el-button v-if="userStore.hasPermission('resource:create')" type="primary" @click="openWizard()">添加资源</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="tab" @tab-change="onTabChange">
        <el-tab-pane label="全部" name="all" />
        <el-tab-pane label="工具" name="tool" />
        <el-tab-pane label="Skills" name="skill" />
        <el-tab-pane label="MCP 连接" name="mcp" />
      </el-tabs>

      <div class="toolbar">
        <el-input v-model="search" clearable placeholder="按名称或 resource_id 搜索" style="width: 260px" @keyup.enter="reloadFirst" />
        <el-select v-model="statusFilter" clearable placeholder="状态" style="width: 140px" @change="reloadFirst">
          <el-option label="online" value="online" />
          <el-option label="offline" value="offline" />
          <el-option label="pending" value="pending" />
        </el-select>
        <el-button @click="reloadFirst">搜索</el-button>
        <span class="hint">共 {{ total }} 条</span>
      </div>

      <el-table v-loading="loading" :data="items" stripe empty-text="暂无该类型资源" @row-click="openDetail">
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <div class="name-cell">
              <strong>{{ row.name }}</strong>
              <el-tag v-if="row.builtin" size="small" type="info">内置只读</el-tag>
            </div>
            <div class="sub">{{ row.description || row.resource_id }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="类型" width="100" />
        <el-table-column label="来源" width="90">
          <template #default="{ row }">{{ row.builtin ? '平台' : '租户' }}</template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="90" />
        <el-table-column prop="health_status" label="健康" width="100">
          <template #default="{ row }">
            <StatusBadge :phase="healthPhase(row.health_status)" :text="row.health_status || 'unknown'" />
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="['tool','skill','mcp'].includes(row.resource_type) && userStore.hasPermission('resource:invoke')"
              link
              type="primary"
              size="small"
              @click.stop="openTrial(row)"
            >试用</el-button>
            <el-button
              v-if="row.resource_type === 'mcp' && userStore.hasPermission('resource:invoke')"
              link
              type="primary"
              size="small"
              @click.stop="openMcpWorkbench(row)"
            >连接</el-button>
            <el-button v-if="userStore.hasPermission('resource:view')" link size="small" @click.stop="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          layout="total, sizes, prev, pager, next"
          :total="total"
          :page-sizes="[20, 50, 100]"
          @current-change="loadData"
          @size-change="reloadFirst"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="showDetail" :title="detail?.name || '资源详情'" size="480px">
      <template v-if="detail">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="resource_id">{{ detail.resource_id }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ detail.resource_type }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ detail.version }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.status }} / {{ detail.health_status }}</el-descriptions-item>
          <el-descriptions-item label="内置">{{ detail.builtin ? '是（只读）' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="说明">{{ detail.description || '—' }}</el-descriptions-item>
        </el-descriptions>
        <p class="hint">调用次数 {{ detail.call_count ?? '—' }}（若无真实来源不展示成功率）</p>
        <el-collapse>
          <el-collapse-item title="输入 Schema" name="in">
            <pre class="payload">{{ pretty(inputSchema(detail)) }}</pre>
          </el-collapse-item>
          <el-collapse-item title="Manifest（已脱敏）" name="mf">
            <pre class="payload">{{ pretty(detail.manifest) }}</pre>
          </el-collapse-item>
        </el-collapse>
        <div class="drawer-actions">
          <el-button v-if="userStore.hasPermission('resource:invoke')" type="primary" @click="openTrial(detail)">试用</el-button>
          <el-button v-if="userStore.hasPermission('resource:view')" @click="runHealth(detail)">健康检查</el-button>
        </div>
        <el-alert
          v-if="!versionsSupported"
          type="info"
          :closable="false"
          title="版本时间线尚未接入本页；调用记录请打开试用台查看。"
          style="margin-top: 12px"
        />
      </template>
    </el-drawer>

    <!-- 试用台 -->
    <el-dialog
      v-model="showTrial"
      :title="`试用 · ${trialRow?.name || ''}`"
      width="min(900px, calc(100vw - 24px))"
      destroy-on-close
      @closed="onTrialClosed"
    >
      <el-row :gutter="16">
        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <div class="panel-title">参数</div>
          <el-radio-group v-model="trialMode" size="small" style="margin-bottom: 8px">
            <el-radio-button value="form">Schema 表单</el-radio-button>
            <el-radio-button value="json">高级 JSON</el-radio-button>
          </el-radio-group>
          <SchemaForm v-show="trialMode === 'form'" ref="schemaFormRef" v-model="trialBody" :schema="trialSchema" />
          <el-input
            v-show="trialMode === 'json'"
            v-model="trialJsonText"
            type="textarea"
            :rows="14"
            @change="syncJsonToBody"
          />
          <el-alert
            v-if="sideEffectHint"
            type="warning"
            :closable="false"
            :title="sideEffectHint"
            style="margin-top: 8px"
          />
        </el-col>
        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <div class="panel-title">结果</div>
          <div v-if="!trialResult" class="hint">尚未调用</div>
          <template v-else>
            <StatusBadge :phase="trialBadgePhase(trialResult)" :text="trialResult.statusText" />
            <p class="hint">
              服务端执行耗时 {{ formatLatencyMs(trialResult.latency_ms) }} ms ·
              浏览器等待耗时 {{ formatLatencyMs(trialResult.browser_latency_ms) }} ms
              <template v-if="trialResult.error_code"> · {{ trialResult.error_code }}</template>
            </p>
            <pre class="payload">{{ pretty(trialResult.summary) }}</pre>
            <el-collapse>
              <el-collapse-item title="原始响应（脱敏视图）" name="raw">
                <pre class="payload">{{ pretty(trialResult.raw) }}</pre>
              </el-collapse-item>
            </el-collapse>
            <el-button size="small" @click="copyTrial">复制 JSON</el-button>
          </template>
        </el-col>
      </el-row>
      <div class="history-block">
        <div class="panel-title">最近调用</div>
        <p v-if="callHistoryLoading" class="hint">正在加载调用历史</p>
        <el-alert
          v-else-if="callHistoryError"
          type="error"
          :closable="false"
          :title="callHistoryError"
        />
        <p v-else-if="!callHistory.length" class="hint">暂无调用记录</p>
        <div v-else class="history-scroll">
          <el-table :data="callHistory" size="small">
            <el-table-column label="状态" min-width="110">
              <template #default="{ row }">
                <StatusBadge :phase="callStatusPhase(row.status)" :text="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="服务端执行耗时" min-width="140">
              <template #default="{ row }">{{ formatLatencyMs(row.latency_ms) }} ms</template>
            </el-table-column>
            <el-table-column prop="version" label="版本" min-width="80" />
            <el-table-column prop="trace_id" label="trace" min-width="160" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" min-width="170" />
            <el-table-column label="错误" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.error_message || '' }}</template>
            </el-table-column>
          </el-table>
          <p class="hint">共 {{ callHistoryTotal }} 条</p>
        </div>
      </div>
      <template #footer>
        <el-button @click="showTrial = false">关闭</el-button>
        <el-button type="primary" :loading="trialLoading" @click="runTrial">实际调用</el-button>
      </template>
    </el-dialog>

    <!-- 注册向导 -->
    <el-dialog v-model="showWizard" title="添加资源" width="760px" destroy-on-close @closed="resetWizard">
      <el-steps :active="wizardStep" finish-status="success" align-center style="margin-bottom: 16px">
        <el-step title="类型" />
        <el-step title="基本信息" />
        <el-step title="参数 / 连接" />
        <el-step title="校验" />
        <el-step title="确认" />
      </el-steps>

      <div v-if="wizardStep === 0">
        <el-radio-group v-model="wizard.kind">
          <el-radio value="tool">工具 Tool — 同步裁判/HTTP 工具</el-radio>
          <el-radio value="skill">Skill — 仅支持已实现的 workflow 类型</el-radio>
          <el-radio value="mcp">MCP — Streamable HTTP 或 stdio 别名</el-radio>
        </el-radio-group>
        <el-alert type="info" :closable="false" style="margin-top: 12px" :title="kindIntro" />
      </div>

      <el-form v-else-if="wizardStep === 1" label-width="110px">
        <el-form-item label="命名空间" required>
          <el-input v-model="wizard.ns" placeholder="如 demo" />
        </el-form-item>
        <el-form-item label="标识" required>
          <el-input v-model="wizard.slug" placeholder="如 my_tool" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="wizard.name" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="wizard.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="wizard.version" />
        </el-form-item>
        <el-form-item label="调用方式">
          <el-select v-model="wizard.call_mode" style="width: 200px">
            <el-option label="sync" value="sync" />
            <el-option label="async（未完整验收）" value="async" disabled />
          </el-select>
        </el-form-item>
        <el-form-item label="幂等" required>
          <el-select v-model="wizard.idempotent" style="width: 320px">
            <el-option label="是：相同请求可安全重试" :value="true" />
            <el-option label="否：重复调用会产生新效果" :value="false" />
          </el-select>
        </el-form-item>
      </el-form>

      <div v-else-if="wizardStep === 2">
        <template v-if="wizard.kind === 'mcp'">
          <el-form label-width="140px">
            <el-form-item label="传输方式" required>
              <el-radio-group v-model="wizard.mcpTransport" @change="onMcpTransportChange">
                <el-radio value="streamable_http">Streamable HTTP</el-radio>
                <el-radio value="stdio">stdio</el-radio>
              </el-radio-group>
            </el-form-item>
            <template v-if="wizard.mcpTransport === 'streamable_http'">
              <el-form-item label="Endpoint" required>
                <el-input v-model="wizard.endpoint" placeholder="https://..." @input="invalidateChecks" />
              </el-form-item>
              <el-form-item label="凭证引用">
                <el-input v-model="wizard.credentialRef" placeholder="环境变量名，不提交明文" @input="invalidateChecks" />
              </el-form-item>
              <el-form-item label="Egress 白名单">
                <el-input v-model="wizard.allowlist" placeholder="host1,host2" @input="invalidateChecks" />
              </el-form-item>
            </template>
            <template v-else>
              <el-form-item label="stdio 别名" required>
                <el-select
                  v-if="stdioAliases.length"
                  v-model="wizard.commandAlias"
                  placeholder="选择允许的服务"
                  style="width: 100%"
                  @change="invalidateChecks"
                >
                  <el-option v-for="alias in stdioAliases" :key="alias" :label="alias" :value="alias" />
                </el-select>
                <el-alert
                  v-else
                  type="warning"
                  :closable="false"
                  title="服务端未配置允许的 stdio 服务，请联系管理员配置"
                />
              </el-form-item>
            </template>
          </el-form>
        </template>
        <template v-else-if="wizard.kind === 'skill'">
          <p class="hint">每一步从已上线工具中选择；第二步可用 $ref 读取上一步 output（例如 s1.output.values）。</p>
          <div v-for="(step, idx) in wizard.skillSteps" :key="idx" class="skill-step">
            <div class="field-row">
              <el-input v-model="step.step_id" placeholder="步骤 ID" style="width: 120px" @input="invalidateChecks" />
              <el-select
                v-model="step.resource_id"
                filterable
                remote
                reserve-keyword
                :remote-method="searchSkillTools"
                :loading="skillToolsLoading"
                placeholder="选择已上线工具"
                no-data-text="暂无已上线工具，请先注册 HTTP 工具"
                style="width: 320px"
                @visible-change="onSkillToolVisible"
                @change="invalidateChecks"
              >
                <el-option
                  v-for="tool in skillToolOptions"
                  :key="tool.resource_id"
                  :label="toolOptionLabel(tool)"
                  :value="tool.resource_id"
                >
                  <div class="opt">
                    <span>{{ tool.name }}</span>
                    <span class="hint">{{ tool.resource_id }} · {{ tool.version }} · {{ tool.health_status || tool.status }}</span>
                  </div>
                </el-option>
              </el-select>
              <el-button v-if="wizard.skillSteps.length > 1" link type="danger" @click="removeSkillStep(idx)">删</el-button>
            </div>
            <el-input
              v-model="step.inputJson"
              type="textarea"
              :rows="4"
              :placeholder="idx === 0 ? DEFAULT_SKILL_INPUTS.s1 : DEFAULT_SKILL_INPUTS.s2"
              @input="invalidateChecks"
              @blur="onSkillInputBlur(step, idx)"
            />
            <p v-if="skillStepErrors[idx]" class="step-error">{{ skillStepErrors[idx] }}</p>
          </div>
          <el-button size="small" @click="addSkillStep">加步骤</el-button>
          <p v-if="skillToolsHasMore" class="hint">下拉列表滚动到底可继续加载下一页。</p>
        </template>
        <template v-else>
          <el-form label-width="120px">
            <el-form-item label="Endpoint" required>
              <el-input v-model="wizard.endpoint" placeholder="https://tool.example/invoke" @input="invalidateChecks" />
            </el-form-item>
            <el-form-item label="方法">
              <el-select v-model="wizard.method" style="width: 160px" @change="invalidateChecks">
                <el-option label="POST" value="POST" />
                <el-option label="GET" value="GET" />
              </el-select>
            </el-form-item>
            <el-form-item label="超时(秒)">
              <el-input-number v-model="wizard.timeout" :min="1" :max="300" :step="1" @change="invalidateChecks" />
            </el-form-item>
            <el-form-item label="凭证引用">
              <el-input v-model="wizard.credentialRef" placeholder="环境变量名，不提交明文" @input="invalidateChecks" />
            </el-form-item>
          </el-form>
          <p class="hint">配置输入 Schema（常见字段）；可切换高级 JSON，切换不丢字段。</p>
          <el-radio-group v-model="wizard.paramMode" size="small" style="margin-bottom: 8px" @change="invalidateChecks">
            <el-radio-button value="form">字段编辑</el-radio-button>
            <el-radio-button value="json">高级 JSON Schema</el-radio-button>
          </el-radio-group>
          <div v-if="wizard.paramMode === 'form'">
            <el-alert
              v-if="wizard.schemaAdvancedKept"
              type="warning"
              :closable="false"
              :title="ADVANCED_SCHEMA_HINT"
              style="margin-bottom: 8px"
            />
            <div v-for="(f, idx) in wizard.fields" :key="idx" class="field-row">
              <el-input v-model="f.key" placeholder="字段名" style="width: 120px" :disabled="wizard.schemaAdvancedKept" @input="invalidateChecks" />
              <el-select v-model="f.type" style="width: 110px" :disabled="wizard.schemaAdvancedKept" @change="invalidateChecks">
                <el-option label="string" value="string" />
                <el-option label="number" value="number" />
                <el-option label="integer" value="integer" />
                <el-option label="boolean" value="boolean" />
              </el-select>
              <el-checkbox v-model="f.required" :disabled="wizard.schemaAdvancedKept" @change="invalidateChecks">必填</el-checkbox>
              <el-button link type="danger" :disabled="wizard.schemaAdvancedKept" @click="wizard.fields.splice(idx, 1); invalidateChecks()">删</el-button>
            </div>
            <el-button size="small" :disabled="wizard.schemaAdvancedKept" @click="wizard.fields.push({ key: '', type: 'string', required: false }); invalidateChecks()">加字段</el-button>
          </div>
          <el-input v-else v-model="wizard.schemaJson" type="textarea" :rows="10" @blur="pullSchemaFromJson" @input="invalidateChecks" />
          <el-alert
            v-if="wizard.paramMode === 'json' && wizard.schemaAdvancedKept"
            type="warning"
            :closable="false"
            :title="ADVANCED_SCHEMA_HINT"
            style="margin-top: 8px"
          />
        </template>
        <el-divider>专业入口</el-divider>
        <el-input v-model="wizard.rawManifest" type="textarea" :rows="6" placeholder="可选：粘贴完整 Manifest JSON，将覆盖向导字段" />
      </div>

      <div v-else-if="wizardStep === 3">
        <el-space direction="vertical" fill style="width: 100%">
          <el-tag :type="checks.schema ? 'success' : 'info'">结构合法：{{ checks.schema ? '通过' : '未测' }}</el-tag>
          <el-tag :type="checks.connect === true ? 'success' : checks.connect === false ? 'danger' : 'info'">
            连接探测：{{ checks.connect === true ? '成功' : checks.connect === false ? '失败' : '未执行' }}
          </el-tag>
          <el-tag type="info">实际调用：未执行（注册后在试用台验证）</el-tag>
        </el-space>
        <el-button style="margin-top: 12px" :loading="checking" @click="runWizardChecks">运行已实现检查</el-button>
        <pre v-if="checkLog" class="payload">{{ checkLog }}</pre>
      </div>

      <div v-else>
        <pre class="payload">{{ pretty(redactManifest(buildManifest())) }}</pre>
        <p class="hint">凭证仅在本次请求提交；列表/详情返回脱敏状态，不回显原文 token。</p>
      </div>

      <template #footer>
        <el-button @click="showWizard = false">取消</el-button>
        <el-button v-if="wizardStep > 0" @click="prevWizard">上一步</el-button>
        <el-button v-if="wizardStep < 4" type="primary" @click="nextWizard">下一步</el-button>
        <el-button
          v-else-if="userStore.hasPermission('resource:create')"
          type="primary"
          :loading="registering"
          @click="submitWizard"
        >确认注册</el-button>
      </template>
    </el-dialog>

    <!-- MCP 工作台 -->
    <el-dialog
      v-model="showProbe"
      class="mcp-workbench"
      title="MCP 连接工作台"
      width="min(920px, calc(100vw - 24px))"
      destroy-on-close
      @closed="clearProbeSecrets"
    >
      <div class="mcp-workbench-body">
        <el-form label-width="120px">
          <el-form-item label="探测来源">
            <el-radio-group v-model="probeMode" @change="onProbeModeChange">
              <el-radio-button value="registered">已注册连接</el-radio-button>
              <el-radio-button value="remote">临时远程地址</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="probeMode === 'registered'" label="资源">
            <el-select v-model="probeForm.resource_id" filterable clearable style="width: 100%" placeholder="选择 MCP 资源" no-data-text="暂无已注册 MCP">
              <el-option v-for="m in mcpOptions" :key="m.resource_id" :label="`${m.name} (${m.resource_id})`" :value="m.resource_id" />
            </el-select>
          </el-form-item>
          <template v-else>
            <el-form-item label="HTTP Endpoint">
              <el-input v-model="probeForm.endpoint" placeholder="https://mcp.example.com/rpc" clearable />
            </el-form-item>
            <el-form-item label="Token">
              <el-input v-model="probeForm.token" type="password" show-password placeholder="关闭面板后清除" />
            </el-form-item>
            <el-form-item label="Egress 白名单">
              <el-input v-model="probeForm.allowlistText" placeholder="host1,host2" />
            </el-form-item>
          </template>
        </el-form>

        <ol class="mcp-steps">
          <li v-for="step in mcpStepViews" :key="step.key" class="mcp-step">
            <el-icon :aria-hidden="true">
              <CircleCheck v-if="step.icon === 'ok'" />
              <CircleClose v-else-if="step.icon === 'fail'" />
              <Warning v-else-if="step.icon === 'warn'" />
              <Minus v-else />
            </el-icon>
            <StatusBadge :phase="step.phase" :text="step.text" />
          </li>
        </ol>

        <el-alert
          v-if="mcpState.stale"
          type="warning"
          :closable="false"
          title="目录已变化，请重新获取"
          style="margin-bottom: 12px"
        />
        <el-alert
          v-if="mcpState.error"
          type="error"
          :closable="false"
          :title="`${mcpState.error.code}：${mcpState.error.message}`"
          style="margin-bottom: 12px"
        >
          <p class="hint">{{ mcpState.error.recovery }}</p>
        </el-alert>

        <el-space wrap>
          <el-button :loading="probeLoading && probeAction === 'initialize'" @click="mcpStep('initialize')">验证连接</el-button>
          <el-button :loading="probeLoading && probeAction === 'tools/list'" @click="mcpStep('tools/list')">获取工具目录</el-button>
        </el-space>

        <p v-if="mcpState.listed && !mcpTools.length" class="hint">工具目录为空</p>
        <p v-else-if="mcpState.negotiated && !mcpTools.length" class="hint">已连接，点击「获取工具目录」加载可用工具</p>
        <el-input
          v-if="mcpTools.length"
          v-model="mcpToolSearch"
          clearable
          placeholder="搜索工具名称或说明"
          style="margin-top: 12px"
        />
        <div v-if="mcpTools.length" class="mcp-table-scroll">
          <el-table :data="filteredMcpTools" size="small" style="margin-top: 8px; min-width: 420px" @row-click="pickMcpTool">
            <el-table-column prop="name" label="工具" min-width="140" />
            <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
          </el-table>
        </div>

        <el-row :gutter="16" class="mcp-call-row">
          <el-col v-if="selectedMcpTool" :xs="24" :sm="24" :md="12">
            <div class="panel-title">调用 {{ selectedMcpTool.name }}</div>
            <SchemaForm
              ref="mcpSchemaRef"
              v-model="mcpCallArgs"
              :schema="selectedMcpTool.inputSchema || { type: 'object', properties: {} }"
            />
            <el-button type="primary" :loading="probeLoading && probeAction === 'tools/call'" @click="mcpCallSelected">测试调用</el-button>
          </el-col>
          <el-col :xs="24" :sm="24" :md="selectedMcpTool ? 12 : 24">
            <div class="panel-title">探测结果</div>
            <p v-if="lastProbeMeta" class="hint">目标：{{ lastProbeMeta.mode }} · {{ lastProbeMeta.target }} · {{ lastProbeMeta.probed_at }}</p>
            <el-input v-if="probeResultText" v-model="probeResultText" type="textarea" :rows="8" readonly class="probe-result" />
            <p v-else class="hint">尚未探测</p>
          </el-col>
        </el-row>

        <div class="history-block">
          <div class="panel-title">最近调用</div>
          <template v-if="probeMode === 'registered'">
            <p v-if="mcpHistoryLoading" class="hint">正在加载调用历史</p>
            <el-alert
              v-else-if="mcpHistoryError"
              type="error"
              :closable="false"
              :title="mcpHistoryError"
            />
            <p v-else-if="!mcpHistory.length" class="hint">暂无调用记录</p>
            <div v-else class="history-scroll">
              <el-table :data="mcpHistory" size="small">
                <el-table-column label="状态" min-width="110">
                  <template #default="{ row }">
                    <StatusBadge :phase="callStatusPhase(row.status)" :text="row.status" />
                  </template>
                </el-table-column>
                <el-table-column label="服务端执行耗时" min-width="140">
                  <template #default="{ row }">{{ formatLatencyMs(row.latency_ms) }} ms</template>
                </el-table-column>
                <el-table-column prop="version" label="版本" min-width="80" />
                <el-table-column prop="trace_id" label="trace" min-width="160" show-overflow-tooltip />
                <el-table-column prop="created_at" label="时间" min-width="170" />
                <el-table-column label="错误" min-width="180" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.error_message || '' }}</template>
                </el-table-column>
              </el-table>
              <p class="hint">共 {{ mcpHistoryTotal }} 条</p>
            </div>
          </template>
          <p v-else class="hint">临时探测记录仅按当前租户保存，不属于已注册资源</p>
        </div>
      </div>
      <template #footer>
        <el-button @click="showProbe = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 批次（保留） -->
    <el-dialog v-model="showBatch" title="冻结批量快照" width="560px">
      <el-form label-width="110px">
        <el-form-item label="数据集">
          <ResourcePicker v-model="batchForm.dataset_id" kind="dataset" />
        </el-form-item>
        <el-form-item label="版本 ID"><el-input-number v-model="batchForm.version_id" :min="0" /></el-form-item>
        <el-form-item label="分片大小"><el-input-number v-model="batchForm.shard_size" :min="1" :max="500" /></el-form-item>
        <el-form-item label="Token 预算"><el-input-number v-model="batchForm.token_budget" :min="0" /></el-form-item>
      </el-form>
      <el-card v-if="batchInfo" shadow="never" class="batch-card">
        <p>batch={{ batchInfo.batch_id }} · 状态 <strong>{{ batchInfo.status }}</strong></p>
        <el-progress :percentage="batchInfo.progress || 0" />
      </el-card>
      <template #footer>
        <el-button @click="closeBatch">关闭</el-button>
        <el-button v-if="batchInfo?.batch_id" @click="refreshBatch">刷新</el-button>
        <el-button v-if="batchInfo?.batch_id && !['success','cancelled'].includes(batchInfo.status)" @click="cancelBatch">取消</el-button>
        <el-button type="primary" :loading="batchLoading" @click="runBatch">创建批次</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, CircleClose, Minus, Warning } from '@element-plus/icons-vue'
import { resourcesApi, batchApi } from '@/api'
import { useUserStore } from '@/stores/user'
import StatusBadge from '@/components/StatusBadge.vue'
import SchemaForm from '@/components/SchemaForm.vue'
import ResourcePicker from '@/components/ResourcePicker.vue'
import {
  buildTrialResult,
  callStatusPhase,
  firstValidationMessage,
  formatLatencyMs,
  pickHistoryLatency,
  trialBadgePhase,
} from '@/utils/resourceTrial'
import {
  ADVANCED_SCHEMA_HINT,
  DEFAULT_SKILL_INPUTS,
  buildManifest as composeManifest,
  emptySkillStep,
  emptyWizard,
  isInvocableTool,
  mcpProbeBody,
  mergeToolPages,
  parseInputJson,
  schemaFormSync,
  schemaFromFields,
  skillCheckNotes,
  toolOptionLabel,
  validateWizardConnect,
} from '@/utils/resourceWizard'
import {
  applyProbeResult,
  emptyMcpState,
  filterMcpTools,
  formatProbeError,
  probeSourceComplete,
  syncSourceState,
} from '@/utils/mcpWorkbench'

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')
const statusFilter = ref('')
const tab = ref('all')
const versionsSupported = false

const showDetail = ref(false)
const detail = ref(null)

const showTrial = ref(false)
const trialRow = ref(null)
const trialMode = ref('form')
const trialBody = ref({})
const trialJsonText = ref('{}')
const trialSchema = ref({ type: 'object', properties: {} })
const trialLoading = ref(false)
const trialResult = ref(null)
const schemaFormRef = ref(null)
const trialCorrelationId = ref('')
const callHistory = ref([])
const callHistoryTotal = ref(0)
const callHistoryLoading = ref(false)
const callHistoryError = ref('')

const showWizard = ref(false)
const wizardStep = ref(0)
const registering = ref(false)
const checking = ref(false)
const checkLog = ref('')
const checks = ref({ schema: false, connect: null })
const wizard = ref(emptyWizard())
const stdioAliases = ref([])
const skillToolOptions = ref([])
const skillToolsLoading = ref(false)
const skillToolsHasMore = ref(false)
const skillToolsPage = ref(1)
const skillToolsQuery = ref('')
const skillStepErrors = ref({})

const showProbe = ref(false)
const probeLoading = ref(false)
const probeAction = ref('')
const probeResultText = ref('')
const probeMode = ref('registered')
const lastProbeMeta = ref(null)
const mcpOptions = ref([])
const mcpTools = ref([])
const selectedMcpTool = ref(null)
const mcpCallArgs = ref({})
const mcpSchemaRef = ref(null)
const mcpToolSearch = ref('')
const mcpState = ref(emptyMcpState())
const mcpHistory = ref([])
const mcpHistoryTotal = ref(0)
const mcpHistoryLoading = ref(false)
const mcpHistoryError = ref('')
const probeForm = ref({
  resource_id: '',
  endpoint: '',
  token: '',
  allowlistText: '',
})

const showBatch = ref(false)
const batchLoading = ref(false)
const batchForm = ref({ dataset_id: null, version_id: 0, shard_size: 50, token_budget: 0 })
const batchInfo = ref(null)
let batchTimer

const kindIntro = computed(() => {
  if (wizard.value.kind === 'mcp') return 'Streamable HTTP 填写 endpoint；stdio 只能选择服务端允许的别名，不能填写任意命令。'
  if (wizard.value.kind === 'skill') return '仅可注册 workflow Skill；每步从已上线工具中选择，并用 JSON 绑定 $ref。'
  return '适合同步 HTTP 工具；副作用需在 Manifest 中声明，试用时会提示确认。'
})

const sideEffectHint = computed(() => {
  const se = trialRow.value?.manifest?.capabilities?.side_effects
  if (!se || se === 'none') return ''
  return `该资源声明副作用：${typeof se === 'string' ? se : JSON.stringify(se)}。将发起真实调用。`
})

const filteredMcpTools = computed(() => filterMcpTools(mcpTools.value, mcpToolSearch.value))

const mcpStepViews = computed(() => {
  const s = mcpState.value
  const configured = probeSourceComplete(probeMode.value, probeForm.value)
  const callPhase = s.lastCall === 'success' ? 'success' : s.lastCall === 'failed' ? 'failed' : 'not_run'
  const callText = s.lastCall === 'success' ? '最近调用成功' : s.lastCall === 'failed' ? '最近调用失败' : '最近调用未执行'
  const listText = s.listed
    ? (s.stale ? `已发现 ${s.toolCount} 个工具（目录已变化，请重新获取）` : `已发现 ${s.toolCount} 个工具`)
    : '尚未发现工具'
  const negotiatedText = s.negotiated
    ? `已协商 ${s.protocolVersion || '未知版本'}${s.serverName ? ` · ${s.serverName}` : ''}`
    : '尚未协商'
  return [
    {
      key: 'source',
      icon: configured ? 'ok' : 'idle',
      phase: configured ? 'configured' : 'unconfigured',
      text: configured ? '已配置' : '未配置',
    },
    {
      key: 'schema',
      icon: s.schemaValid ? 'ok' : 'idle',
      phase: s.schemaValid ? 'schema_valid' : 'schema_invalid',
      text: s.schemaValid ? '结构有效' : '结构未通过',
    },
    {
      key: 'negotiate',
      icon: s.negotiated ? 'ok' : 'idle',
      phase: s.negotiated ? 'negotiated' : 'not_run',
      text: negotiatedText,
    },
    {
      key: 'list',
      icon: s.stale ? 'warn' : s.listed ? 'ok' : 'idle',
      phase: s.stale ? 'stale' : s.listed ? 'listed' : 'not_run',
      text: listText,
    },
    {
      key: 'call',
      icon: s.lastCall === 'success' ? 'ok' : s.lastCall === 'failed' ? 'fail' : 'idle',
      phase: callPhase,
      text: callText,
    },
  ]
})

function pretty(v) {
  try {
    return JSON.stringify(v ?? {}, null, 2)
  } catch {
    return String(v)
  }
}

function healthPhase(h) {
  if (h === 'online') return 'completed'
  if (h === 'abnormal') return 'failed'
  return 'idle'
}

function inputSchema(row) {
  return row?.manifest?.capabilities?.input_schema || { type: 'object', properties: {} }
}

function typeFromTab(t) {
  if (t === 'all') return ''
  return t
}

async function loadData() {
  loading.value = true
  try {
    const res = await resourcesApi.list({
      page: page.value,
      page_size: pageSize.value,
      resource_type: typeFromTab(tab.value),
      status: statusFilter.value || undefined,
      search: search.value || undefined,
    })
    items.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function reloadFirst() {
  page.value = 1
  loadData()
  syncRoute()
}

function onTabChange() {
  reloadFirst()
}

function syncRoute() {
  router.replace({
    path: '/resources',
    query: {
      tab: tab.value !== 'all' ? tab.value : undefined,
      resource: detail.value?.resource_id || route.query.resource || undefined,
      q: search.value || undefined,
      page: page.value > 1 ? String(page.value) : undefined,
    },
  })
}

async function openDetail(row) {
  if (!row) return
  try {
    detail.value = await resourcesApi.get(row.resource_id || row)
    showDetail.value = true
    syncRoute()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '加载详情失败')
  }
}

async function runHealth(row) {
  const res = await resourcesApi.health(row.resource_id)
  ElMessage[res.ok ? 'success' : 'warning'](res.detail || res.status)
  if (detail.value?.resource_id === row.resource_id) {
    detail.value = { ...detail.value, health_status: res.status || (res.ok ? 'online' : 'abnormal') }
  }
}

function openTrial(row) {
  trialRow.value = row
  trialSchema.value = inputSchema(row)
  const defaults = {}
  const propsMap = trialSchema.value.properties || {}
  for (const [k, def] of Object.entries(propsMap)) {
    if (def && def.default !== undefined) defaults[k] = def.default
  }
  if (row.resource_type === 'mcp') {
    trialBody.value = { method: 'initialize', id: 1, ...defaults }
  } else {
    trialBody.value = { ...defaults }
  }
  trialJsonText.value = pretty(trialBody.value)
  trialResult.value = null
  trialCorrelationId.value = ''
  callHistory.value = []
  callHistoryTotal.value = 0
  callHistoryError.value = ''
  trialMode.value = Object.keys(propsMap).length ? 'form' : 'json'
  showTrial.value = true
  loadCallHistory()
}

async function loadCallHistory() {
  if (!trialRow.value) return
  callHistoryLoading.value = true
  callHistoryError.value = ''
  try {
    const result = await resourcesApi.calls(trialRow.value.resource_id, {
      page: 1, page_size: 10,
    })
    callHistory.value = result.items || []
    callHistoryTotal.value = result.total || 0
    if (trialResult.value) {
      trialResult.value = {
        ...trialResult.value,
        latency_ms: pickHistoryLatency(callHistory.value, trialCorrelationId.value),
      }
    }
  } catch (error) {
    callHistoryError.value = error?.response?.data?.message || error.message
  } finally {
    callHistoryLoading.value = false
  }
}

function syncJsonToBody() {
  try {
    trialBody.value = JSON.parse(trialJsonText.value || '{}')
  } catch (e) {
    ElMessage.error(`JSON 无效：${e.message}`)
  }
}

watch(trialBody, (v) => {
  if (trialMode.value === 'form') trialJsonText.value = pretty(v)
}, { deep: true })

watch(trialMode, (mode) => {
  if (mode === 'json') trialJsonText.value = pretty(trialBody.value)
  if (mode === 'form') {
    try {
      trialBody.value = JSON.parse(trialJsonText.value || '{}')
    } catch { /* keep */ }
  }
})

watch(
  () => `${probeMode.value}|${probeForm.value.resource_id}|${String(probeForm.value.endpoint || '').trim()}`,
  async (key, previous) => {
    if (previous && key !== previous) {
      mcpState.value = emptyMcpState()
      mcpTools.value = []
      selectedMcpTool.value = null
      mcpCallArgs.value = {}
    }
    refreshMcpSourceState()
    if (showProbe.value && probeMode.value === 'registered' && probeForm.value.resource_id) {
      await applyRegisteredCatalog(probeForm.value.resource_id)
      await loadMcpHistory()
    }
  },
)

async function runTrial() {
  if (!trialRow.value) return
  if (trialMode.value === 'json') {
    try {
      trialBody.value = JSON.parse(trialJsonText.value || '{}')
    } catch (e) {
      ElMessage.error(`JSON 无效，未发送：${e.message}`)
      return
    }
  } else if (schemaFormRef.value) {
    const validation = schemaFormRef.value.validate()
    if (!validation.ok) {
      ElMessage.error(firstValidationMessage(validation))
      return
    }
  }
  if (sideEffectHint.value) {
    try {
      await ElMessageBox.confirm(sideEffectHint.value, '确认真实调用', { type: 'warning' })
    } catch {
      return
    }
  }
  trialLoading.value = true
  trialResult.value = null
  const started = performance.now()
  const correlationId = `trial-${Date.now()}`
  trialCorrelationId.value = correlationId
  try {
    const res = await resourcesApi.invoke({
      resource_id: trialRow.value.resource_id,
      body: trialBody.value,
      correlation_id: correlationId,
    })
    trialResult.value = buildTrialResult(res, performance.now() - started)
    if (trialResult.value.ok) ElMessage.success(trialResult.value.statusText)
    else ElMessage.error(trialResult.value.statusText)
  } catch (e) {
    trialResult.value = {
      ok: false,
      status: 'failed',
      statusText: '请求失败',
      latency_ms: null,
      browser_latency_ms: Math.round(performance.now() - started),
      error_code: e?.response?.status || '',
      summary: e?.response?.data || e?.message,
      raw: e?.response?.data || String(e),
    }
    ElMessage.error(String(e?.response?.data?.message || e?.message || e))
  } finally {
    trialLoading.value = false
    await loadCallHistory()
  }
}

function copyTrial() {
  navigator.clipboard?.writeText(pretty(trialResult.value?.raw))
  ElMessage.success('已复制')
}

function onTrialClosed() {
  trialRow.value = null
  trialResult.value = null
  trialCorrelationId.value = ''
  callHistory.value = []
  callHistoryTotal.value = 0
  callHistoryError.value = ''
}

function openWizard() {
  wizard.value = emptyWizard()
  wizardStep.value = 0
  checks.value = { schema: false, connect: null }
  checkLog.value = ''
  skillStepErrors.value = {}
  skillToolOptions.value = []
  stdioAliases.value = []
  showWizard.value = true
}

function resetWizard() {
  wizard.value.token = ''
}

function schemaFromFieldsLocal() {
  return schemaFromFields(wizard.value.fields)
}

function pullSchemaFromJson() {
  const result = schemaFormSync(wizard.value.schemaJson, wizard.value.fields)
  wizard.value.schemaAdvancedKept = result.advancedKept
  if (!result.advancedKept) wizard.value.fields = result.fields
  if (result.error) ElMessage.error(result.error)
  invalidateChecks()
}

function allowedSkillToolIds() {
  return new Set(skillToolOptions.value.map((item) => item.resource_id).filter(Boolean))
}

function wizardContext() {
  return {
    ...wizard.value,
    stdioAliases: stdioAliases.value,
    allowedToolIds: allowedSkillToolIds(),
  }
}

function buildManifest() {
  return composeManifest(wizardContext())
}

function redactManifest(mf) {
  const walk = (node) => {
    if (Array.isArray(node)) return node.map(walk)
    if (node && typeof node === 'object') {
      const out = {}
      for (const [k, v] of Object.entries(node)) {
        if (['token', 'api_key', 'apikey', 'secret', 'password', 'authorization'].includes(String(k).toLowerCase()) && v) {
          out[k] = { configured: true, redacted: true }
        } else {
          out[k] = walk(v)
        }
      }
      return out
    }
    return node
  }
  return walk(mf)
}

function invalidateChecks() {
  checks.value = { schema: false, connect: null }
  checkLog.value = ''
}

async function loadStdioAliases() {
  try {
    const res = await resourcesApi.stdioAliases()
    stdioAliases.value = Array.isArray(res.items) ? res.items : []
  } catch (error) {
    stdioAliases.value = []
    ElMessage.error(error?.response?.data?.message || error.message || '无法加载 stdio 别名')
  }
}

async function onMcpTransportChange() {
  invalidateChecks()
  wizard.value.commandAlias = ''
  if (wizard.value.mcpTransport === 'stdio') await loadStdioAliases()
}

function addSkillStep() {
  wizard.value.skillSteps.push(emptySkillStep(wizard.value.skillSteps.length + 1))
  invalidateChecks()
}

function removeSkillStep(idx) {
  wizard.value.skillSteps.splice(idx, 1)
  invalidateChecks()
}

function onSkillInputBlur(step, idx) {
  const parsed = parseInputJson(step.inputJson, step.inputJson)
  const next = { ...skillStepErrors.value }
  if (!parsed.ok) next[idx] = parsed.error
  else delete next[idx]
  skillStepErrors.value = next
}

async function loadSkillTools({ reset = false, search = skillToolsQuery.value } = {}) {
  if (skillToolsLoading.value && !reset) return
  const selectedIds = new Set(
    (wizard.value.skillSteps || []).map((step) => step.resource_id).filter(Boolean),
  )
  const kept = reset
    ? skillToolOptions.value.filter((item) => selectedIds.has(item.resource_id))
    : skillToolOptions.value
  if (reset) {
    skillToolsPage.value = 1
    skillToolOptions.value = kept
    skillToolsHasMore.value = false
  }
  skillToolsLoading.value = true
  try {
    const page = skillToolsPage.value
    const res = await resourcesApi.list({
      resource_type: 'tool',
      page,
      page_size: 50,
      search: search || undefined,
    })
    const merged = mergeToolPages(kept, {
      items: (res.items || []).filter(isInvocableTool),
      page,
      page_size: 50,
      total: res.total || 0,
    })
    skillToolOptions.value = merged.items
    skillToolsHasMore.value = merged.hasMore
    skillToolsPage.value = merged.nextPage
  } finally {
    skillToolsLoading.value = false
  }
}

function searchSkillTools(query) {
  skillToolsQuery.value = query
  loadSkillTools({ reset: true, search: query })
}

function bindSkillToolScroll() {
  const wraps = document.querySelectorAll('.el-select-dropdown__wrap')
  const wrap = wraps[wraps.length - 1]
  if (!wrap || wrap.dataset.skillPageBound) return
  wrap.dataset.skillPageBound = '1'
  wrap.addEventListener('scroll', () => {
    if (wrap.scrollTop + wrap.clientHeight < wrap.scrollHeight - 24) return
    if (skillToolsHasMore.value && !skillToolsLoading.value) {
      loadSkillTools({ search: skillToolsQuery.value })
    }
  })
}

function onSkillToolVisible(visible) {
  if (!visible) return
  if (!skillToolOptions.value.length) loadSkillTools({ reset: true, search: skillToolsQuery.value })
  requestAnimationFrame(bindSkillToolScroll)
}

watch(
  [wizardStep, () => wizard.value.kind, () => wizard.value.mcpTransport],
  ([step, kind, transport]) => {
    if (step !== 2) return
    if (kind === 'mcp' && transport === 'stdio') loadStdioAliases()
    if (kind === 'skill') loadSkillTools({ reset: true })
  },
)

function prevWizard() {
  checks.value = { schema: false, connect: null }
  checkLog.value = ''
  wizardStep.value -= 1
}

function manifestGaps(mf) {
  const missing = []
  if (!mf?.resource_id) missing.push('resource_id')
  if (!mf?.name) missing.push('name')
  if (!mf?.resource_type) missing.push('resource_type')
  if (!mf?.owner?.name) missing.push('owner.name')
  const caps = mf?.capabilities
  if (!caps || typeof caps !== 'object') missing.push('capabilities')
  else {
    if (!caps.input_schema || typeof caps.input_schema !== 'object') missing.push('capabilities.input_schema')
    if (!caps.output_schema || typeof caps.output_schema !== 'object') missing.push('capabilities.output_schema')
    if (!['sync', 'async', 'stream', 'batch'].includes(caps.call_mode)) missing.push('capabilities.call_mode')
    if (!Object.prototype.hasOwnProperty.call(caps, 'idempotent')) missing.push('capabilities.idempotent')
    if (!Number.isInteger(caps.timeout)) missing.push('capabilities.timeout')
  }
  if (!mf?.interfaces || typeof mf.interfaces !== 'object') missing.push('interfaces')
  return missing
}

function nextWizard() {
  if (wizardStep.value === 0 && !wizard.value.kind) return
  if (wizardStep.value === 1) {
    if (!wizard.value.ns || !wizard.value.slug || !wizard.value.name) {
      ElMessage.warning('请填写命名空间、标识与名称')
      return
    }
  }
  if (wizardStep.value === 2) {
    const connect = validateWizardConnect(wizardContext())
    if (!connect.ok) {
      ElMessage.warning(connect.message)
      if (connect.errors) {
        const mapped = {}
        wizard.value.skillSteps.forEach((step, idx) => {
          const hit = connect.errors.find((msg) => msg.includes(step.step_id || `s${idx + 1}`))
          if (hit) mapped[idx] = hit
        })
        skillStepErrors.value = mapped
      }
      return
    }
    if (wizard.value.paramMode === 'form' && wizard.value.kind !== 'skill' && !wizard.value.schemaAdvancedKept) {
      wizard.value.schemaJson = pretty(schemaFromFieldsLocal())
    }
    try {
      buildManifest()
    } catch (e) {
      ElMessage.error(`Manifest 无法构建：${e.message}`)
      return
    }
  }
  wizardStep.value += 1
}

async function runWizardChecks() {
  checking.value = true
  checkLog.value = ''
  checks.value = { schema: false, connect: null }
  try {
    const mf = buildManifest()
    const missing = manifestGaps(mf)
    checks.value.schema = missing.length === 0
    checkLog.value += checks.value.schema
      ? '结构检查：OK（与后端必填字段对齐；不等于连接或调用成功）\n'
      : `结构检查 FAIL，缺少：${missing.join('、')}\n`
    if (wizard.value.kind === 'mcp') {
      try {
        const res = await resourcesApi.mcpProbe(mcpProbeBody(wizard.value))
        checks.value.connect = !!res.ok
        checkLog.value += `连接探测：${checks.value.connect ? 'OK' : 'FAIL'} target=${res.target} transport=${res.transport || wizard.value.mcpTransport}\n`
      } catch (e) {
        checks.value.connect = false
        checkLog.value += `连接探测失败：${e?.response?.data?.message || e.message}\n`
      }
    } else if (wizard.value.kind === 'tool') {
      checkLog.value += '连接探测：工具仅做结构检查，未执行调用（保持未执行）\n'
    } else if (wizard.value.kind === 'skill') {
      const notes = skillCheckNotes(wizard.value.skillSteps)
      checkLog.value += `${notes.message}\n`
    } else {
      checkLog.value += '连接探测：跳过（保持未执行）\n'
    }
  } catch (e) {
    checkLog.value += String(e.message || e)
  } finally {
    checking.value = false
  }
}

async function submitWizard() {
  registering.value = true
  try {
    const mf = buildManifest()
    const res = await resourcesApi.register(mf)
    ElMessage.success('已注册')
    showWizard.value = false
    wizard.value.token = ''
    await loadData()
    openDetail(res)
    if (userStore.hasPermission('resource:invoke')) openTrial(res)
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '注册失败')
  } finally {
    registering.value = false
  }
}

function onProbeModeChange() {
  if (probeMode.value === 'registered') {
    probeForm.value.endpoint = ''
    probeForm.value.token = ''
    probeForm.value.allowlistText = ''
  } else {
    probeForm.value.resource_id = ''
  }
  resetMcpStates()
}

function resetMcpStates() {
  mcpState.value = emptyMcpState()
  mcpTools.value = []
  selectedMcpTool.value = null
  mcpCallArgs.value = {}
  mcpToolSearch.value = ''
  probeResultText.value = ''
  lastProbeMeta.value = null
  mcpHistory.value = []
  mcpHistoryTotal.value = 0
  mcpHistoryError.value = ''
  refreshMcpSourceState()
}

function refreshMcpSourceState(catalogStale) {
  mcpState.value = syncSourceState(mcpState.value, {
    mode: probeMode.value,
    form: probeForm.value,
    catalogStale,
  })
}

function clearProbeSecrets() {
  probeForm.value.token = ''
  resetMcpStates()
}

async function loadMcpHistory() {
  if (probeMode.value !== 'registered' || !probeForm.value.resource_id) {
    mcpHistory.value = []
    mcpHistoryTotal.value = 0
    mcpHistoryError.value = ''
    return
  }
  mcpHistoryLoading.value = true
  mcpHistoryError.value = ''
  try {
    const result = await resourcesApi.calls(probeForm.value.resource_id, {
      page: 1,
      page_size: 10,
    })
    mcpHistory.value = result.items || []
    mcpHistoryTotal.value = result.total || 0
  } catch (error) {
    mcpHistoryError.value = error?.response?.data?.message || error.message || '调用历史加载失败'
  } finally {
    mcpHistoryLoading.value = false
  }
}

async function applyRegisteredCatalog(resourceId) {
  if (!resourceId) return
  try {
    const detailRow = await resourcesApi.get(resourceId)
    refreshMcpSourceState(Boolean(detailRow?.mcp_catalog?.stale))
  } catch (error) {
    mcpState.value = {
      ...mcpState.value,
      error: formatProbeError(null, error),
    }
  }
}

async function openMcpWorkbench(row) {
  resetMcpStates()
  const list = await resourcesApi.list({ resource_type: 'mcp', page_size: 100 })
  mcpOptions.value = list.items || []
  if (row?.resource_id) {
    probeMode.value = 'registered'
    probeForm.value.resource_id = row.resource_id
    probeForm.value.endpoint = ''
    refreshMcpSourceState(Boolean(row?.mcp_catalog?.stale))
    await applyRegisteredCatalog(row.resource_id)
    await loadMcpHistory()
  } else if (!probeForm.value.resource_id && !probeForm.value.endpoint) {
    probeMode.value = 'remote'
    refreshMcpSourceState()
  }
  showProbe.value = true
}

function probePayload(extra = {}) {
  if (probeMode.value === 'registered') {
    return {
      resource_id: probeForm.value.resource_id.trim(),
      ...extra,
    }
  }
  return {
    endpoint: probeForm.value.endpoint.trim(),
    token: probeForm.value.token || '',
    egress_allowlist: probeForm.value.allowlistText.trim()
      ? probeForm.value.allowlistText.split(',').map((s) => s.trim()).filter(Boolean)
      : [],
    ...extra,
  }
}

function applyMcpOutcome(method, res, caught) {
  const outcome = applyProbeResult(mcpState.value, method, res, caught)
  mcpState.value = outcome.state
  if (outcome.tools) mcpTools.value = outcome.tools
  if (method === 'initialize' || (method === 'tools/list' && !outcome.success)) {
    mcpTools.value = outcome.tools || []
    selectedMcpTool.value = null
    mcpCallArgs.value = {}
  }
  if (res) {
    lastProbeMeta.value = { mode: res.mode, target: res.target, probed_at: res.probed_at }
    probeResultText.value = pretty({
      ok: res.ok,
      mode: res.mode,
      target: res.target,
      session: res.session,
      error: res.error,
      result: res.result,
      notifications: res.notifications,
    })
  } else if (caught) {
    probeResultText.value = pretty(mcpState.value.error)
  }
  return outcome
}

async function mcpStep(method) {
  probeLoading.value = true
  probeAction.value = method
  try {
    const res = await resourcesApi.mcpProbe(probePayload({ method, params: {} }))
    const outcome = applyMcpOutcome(method, res)
    if (outcome.success) {
      if (method === 'initialize') ElMessage.success('连接验证完成')
      if (method === 'tools/list') ElMessage.success(`发现 ${mcpState.value.toolCount} 个工具`)
    } else {
      ElMessage.error(`${mcpState.value.error?.code || 'MCP_PROTOCOL_ERROR'}：${mcpState.value.error?.message || '探测失败'}`)
    }
  } catch (e) {
    applyMcpOutcome(method, null, e)
    ElMessage.error(`${mcpState.value.error?.code || 'MCP_TRANSPORT_ERROR'}：${mcpState.value.error?.message || '请求失败'}`)
  } finally {
    probeLoading.value = false
    probeAction.value = ''
  }
}

function pickMcpTool(row) {
  selectedMcpTool.value = row
  mcpCallArgs.value = {}
}

async function mcpCallSelected() {
  if (!selectedMcpTool.value) return
  const validation = mcpSchemaRef.value?.validate()
  if (validation && !validation.ok) {
    ElMessage.error(firstValidationMessage(validation))
    return
  }
  probeLoading.value = true
  probeAction.value = 'tools/call'
  try {
    const res = await resourcesApi.mcpProbe(
      probePayload({
        method: 'tools/call',
        params: { name: selectedMcpTool.value.name, arguments: mcpCallArgs.value },
      }),
    )
    const outcome = applyMcpOutcome('tools/call', res)
    if (outcome.success) ElMessage.success('工具调用成功')
    else ElMessage.error(`${mcpState.value.error?.code || 'MCP_TOOL_ERROR'}：${mcpState.value.error?.message || '调用失败'}`)
    if (probeMode.value === 'registered') await loadMcpHistory()
  } catch (e) {
    applyMcpOutcome('tools/call', null, e)
    ElMessage.error(`${mcpState.value.error?.code || 'MCP_TRANSPORT_ERROR'}：${mcpState.value.error?.message || '请求失败'}`)
  } finally {
    probeLoading.value = false
    probeAction.value = ''
  }
}

async function runBatch() {
  if (!batchForm.value.dataset_id) {
    ElMessage.warning('请选择数据集')
    return
  }
  batchLoading.value = true
  try {
    const payload = {
      dataset_id: batchForm.value.dataset_id,
      shard_size: batchForm.value.shard_size,
      token_budget: batchForm.value.token_budget || 0,
    }
    if (batchForm.value.version_id) payload.version_id = batchForm.value.version_id
    batchInfo.value = await batchApi.run(payload)
    ElMessage.success('已创建批次')
    startBatchPoll()
  } finally {
    batchLoading.value = false
  }
}

async function refreshBatch() {
  if (!batchInfo.value?.batch_id) return
  batchInfo.value = await batchApi.status(batchInfo.value.batch_id)
}

async function cancelBatch() {
  if (!batchInfo.value?.batch_id) return
  await batchApi.cancel(batchInfo.value.batch_id)
  await refreshBatch()
  ElMessage.success('已取消')
}

function startBatchPoll() {
  clearInterval(batchTimer)
  let inFlight = false
  const tick = async () => {
    if (!batchInfo.value?.batch_id || inFlight) return
    if (['success', 'cancelled', 'paused_budget', 'failed'].includes(batchInfo.value.status)) {
      clearInterval(batchTimer)
      batchTimer = null
      return
    }
    inFlight = true
    try {
      await refreshBatch()
    } finally {
      inFlight = false
    }
  }
  batchTimer = setInterval(tick, 3000)
}

function closeBatch() {
  clearInterval(batchTimer)
  showBatch.value = false
}

onMounted(async () => {
  if (route.query.tab) tab.value = String(route.query.tab)
  if (route.query.q) search.value = String(route.query.q)
  if (route.query.page) page.value = Number(route.query.page) || 1
  await loadData()
  if (route.query.resource) {
    try {
      await openDetail(String(route.query.resource))
    } catch { /* */ }
  }
})

onUnmounted(() => clearInterval(batchTimer))
</script>

<style scoped>
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.pager { display: flex; justify-content: flex-end; margin-top: 12px; }
.name-cell { display: flex; align-items: center; gap: 8px; }
.sub { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); }
.payload {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 280px;
  overflow: auto;
  background: #f8fafc;
  padding: 8px;
  border-radius: 8px;
}
.panel-title { font-weight: 600; margin-bottom: 8px; }
.history-block { margin-top: 16px; }
.history-scroll { overflow-x: auto; max-width: 100%; }
.resources-page { overflow-x: hidden; }
.mcp-workbench-body { padding-bottom: 8px; }
.mcp-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
}
.mcp-step {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
}
.mcp-table-scroll { overflow-x: auto; max-width: 100%; margin-top: 4px; }
.mcp-call-row { margin-top: 12px; }
@media (max-width: 420px) {
  .mcp-workbench-body { padding-bottom: 16px; }
}
.drawer-actions { display: flex; gap: 8px; margin-top: 12px; }
.field-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.skill-step { margin-bottom: 12px; }
.step-error { color: var(--el-color-danger); font-size: 12px; margin: 4px 0 0; }
.opt { display: flex; justify-content: space-between; gap: 12px; width: 100%; }
.batch-card { margin-top: 8px; font-size: 13px; }
.probe-result { margin-top: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
</style>
