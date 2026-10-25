<template>
  <div class="agents-wb" :class="{ 'focus-reading': focusReading }">
    <div class="page-header">
      <div>
        <h2 class="page-title">评测助手</h2>
        <p class="page-desc">描述目标，核对计划，确认执行。助手会持续跟进任务，并在关键节点主动更新。</p>
      </div>
      <el-button v-if="userStore.hasPermission('agent:list')" @click="settingsOpen = true">助手设置</el-button>
    </div>

    <el-drawer v-model="settingsOpen" title="助手设置" size="min(760px, 94vw)">    <el-card class="profile-card" shadow="never">
      <el-collapse v-model="profilePanel">
        <el-collapse-item title="助手行为与工具" name="profile">
          <p class="hint">提示词在每次运行时作为系统提示。当前计划、已启用能力和工具规则会附在后面。创建任务和执行恢复仍须在下方确认。</p>
          <el-input
            v-model="profileForm.system_prompt"
            type="textarea"
            :rows="4"
            :disabled="!canEditProfile"
          />
          <el-form label-width="120px" class="profile-form">
            <el-form-item label="模型名">
              <el-input v-model="profileForm.model_name" placeholder="留空则用规划模型自己的名称" :disabled="!canEditProfile" />
            </el-form-item>
            <el-form-item label="采样温度">
              <el-input-number v-model="profileForm.temperature" :min="0" :max="2" :step="0.1" :disabled="!canEditProfile" />
            </el-form-item>
            <el-form-item label="单次输出上限">
              <el-input-number v-model="profileForm.max_tokens" :min="0" :max="8192" :step="64" :disabled="!canEditProfile" />
              <span class="hint">0 表示不额外截断。大于 0 时，模型请求和最终回复都受这个上限约束。</span>
            </el-form-item>
            <el-form-item label="模型决策上限">
              <el-input-number v-model="profileForm.max_iterations" :min="1" :max="20" :disabled="!canEditProfile" />
            </el-form-item>
            <el-form-item label="单次模型超时">
              <el-input-number v-model="profileForm.timeout_seconds" :min="5" :max="600" :disabled="!canEditProfile" />
              <span class="hint">秒。超时后终止该次调用，并把失败返回主 Agent。</span>
            </el-form-item>
            <el-form-item label="实时执行动态">
              <el-switch v-model="profileForm.supports_stream" :disabled="!canEditProfile" />
              <span class="hint">开启后通过SSE及时显示已提交的执行事件和完整回复；断线自动接续。当前不逐字输出模型文本。</span>
            </el-form-item>
            <el-form-item label="人工介入">
              <el-tag type="success">关键操作始终需确认</el-tag><span class="hint">创建并执行任务、配置变更后的执行、恢复与补测需要人员确认；助手分析不会替你自动批准，也不支持任意节点的手动接管。</span>
            </el-form-item>
            <el-form-item label="可调用工具">
              <el-checkbox-group v-model="profileForm.available_tools" :disabled="!canEditProfile">
                <el-checkbox v-for="tool in mainToolOptions" :key="tool.name" :label="tool.name">{{ tool.label }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

          </el-form>
          <el-button
            v-if="canEditProfile"
            type="primary"
            size="small"
            :loading="profileSaving"
            @click="saveProfile"
          >保存</el-button>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <el-card class="profile-card" shadow="never">
      <el-collapse v-model="catalogPanel">
        <el-collapse-item title="子 Agent 与编排 Skill" name="catalog">
      <div class="plan-head">
        <div class="plan-title">子 Agent</div>
        <el-button v-if="canEditProfile" link type="primary" @click="openAgentEditor()">添加</el-button>
      </div>
      <p class="hint">每个子 Agent 使用自己的工具和 Skill。监控分析、异常诊断不能删除。停用后不会出现在新建评测的可选项里。</p>
      <el-table :data="catalog.subagents" size="small">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column label="工具" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ toolLabels(row.available_tools) }}</template>
        </el-table-column>
        <el-table-column label="Skill" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ skillLabels(row.skill_codes) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ agentStatus(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button v-if="canEditProfile" link @click="openAgentEditor(row)">编辑</el-button>
            <el-button v-if="canEditProfile && row.enabled === false" link @click="restoreAgent(row)">恢复</el-button>
            <el-button v-else-if="canEditProfile" link type="danger" :disabled="row.required" @click="removeAgent(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="plan-head skill-head">
        <div class="plan-title">编排 Skill</div>
        <el-button v-if="canEditProfile" link type="primary" @click="openSkillEditor()">添加</el-button>
      </div>
      <el-table :data="catalog.skills" size="small">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="code" label="标识" min-width="140" />
        <el-table-column label="执行方式" width="120">
          <template #default="{ row }">{{ executionLabel(row.execution_type) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ row.enabled === false ? '已停用' : (row.builtin ? '内置' : '自定义') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button v-if="canEditProfile" link @click="openSkillEditor(row)">编辑</el-button>
            <el-button v-if="canEditProfile && row.enabled === false" link @click="restoreSkill(row)">恢复</el-button>
            <el-button v-else-if="canEditProfile" link type="danger" @click="removeSkill(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    </el-drawer>

    <div class="wb-layout">
      <aside class="session-rail" :class="{ collapsed: railCollapsed }">
        <div class="rail-head">
          <span>评测会话</span>
          <el-button link size="small" @click="railCollapsed = !railCollapsed">{{ railCollapsed ? '展开' : '收起' }}</el-button>
        </div>
        <div v-if="!railCollapsed" class="rail-scroll">
          <el-button
            v-if="userStore.hasPermission('agent:invoke')"
            type="primary"
            plain
            class="new-btn"
            @click="startNew"
          >新建评测</el-button>
          <el-input v-model="sessionQuery" placeholder="搜索会话" clearable size="small" class="session-search" />
          <div v-if="sessionsLoadError" class="rail-empty">{{ sessionsLoadError }}</div>
          <div v-else-if="!sessions.length" class="rail-empty">暂无会话</div>
          <button
            v-for="s in filteredSessions"
            :key="s.id"
            type="button"
            class="sess-item"
            :class="{ active: currentId === s.id }" :aria-current="currentId === s.id ? 'page' : undefined"
            @click="selectSession(s.id)"
          >
            <div class="sess-title">#{{ s.id }} {{ s.title || '未命名' }}</div>
            <div class="sess-meta"><span class="state-dot" :class="sessionState(s).tone"></span><span :class="sessionState(s).tone">{{ sessionState(s).label }}</span><span v-if="s.task_id">任务 #{{ s.task_id }}</span></div>
          </button>
        </div>
      </aside>

      <main class="main-pane">
        <!-- 无会话：起步 -->
        <section v-if="!currentId" class="hero-card">
          <div class="hero-kicker">新建评测</div><h3>这次想评测什么？</h3><p class="hint">说明场景、数据和目标。助手先检索实际资源并生成计划，未经确认不会执行任务。</p>
          <el-input
            v-model="goalText"
            type="textarea"
            :rows="4"
            placeholder="例如：对金融场景做智能对话正式评测，使用已发布数据集与已配置连接的模型"
          />
          <div class="prep">
            <div class="prep-row">
              <span>助手使用的规划模型</span>
              <StatusBadge v-if="plannerModels.length" phase="approved" text="已配置" />
              <StatusBadge v-else phase="failed" text="真实模型未配置" />
              <router-link v-if="userStore.hasPermission('model:create')" class="link" to="/models">去配置模型</router-link>
            </div>
            <div class="prep-row hint">规划模型负责理解需求与编排，被测模型在计划中另外选择。</div>
          </div>
          <el-collapse v-model="budgetPanel">
            <el-collapse-item title="评测准备：规划模型与预算（必填）" name="adv">
              <el-form label-width="100px" size="small">
                <el-form-item label="Token 预算">
                  <el-input-number v-model="tokenBudget" :min="0" />
                  <div class="hint">0 表示后端按未设限额处理；正式评测建议 &gt;0</div>
                </el-form-item>
                <el-form-item label="规划模型">
                  <el-select v-model="plannerModelId" clearable filterable placeholder="必选" style="width: 100%">
                    <el-option v-for="m in plannerModels" :key="m.id" :label="m.name" :value="m.id" />
                  </el-select>
                  <div v-if="modelsLoadError" class="hint">{{ modelsLoadError }}</div>
                </el-form-item>
                <el-form-item label="复用上次编排">
                  <el-select v-model="recipeId" clearable filterable placeholder="选择已沉淀的经验" style="width: 100%" @change="applyRecipe">
                    <el-option v-for="recipe in recipes" :key="recipe.id" :label="recipe.title || recipe.requirement" :value="recipe.id" />
                  </el-select>
                  <div class="hint">选中后会填入目标、预算、子 Agent、Skill 和 MCP。日常新建可以不展开这里。</div>
                </el-form-item>
              </el-form>
            </el-collapse-item>
          </el-collapse>
          <el-collapse class="cap-card"><el-collapse-item title="可选能力：子 Agent、Skill 与 MCP" name="capabilities">
            <div class="plan-title">子 Agent</div>
            <p class="hint">监控分析和异常诊断始终启用。其余角色在主 Agent 需要时调用。自定义角色只做分析，不直接改任务。</p>
            <el-checkbox-group v-model="selectedRoles">
              <el-checkbox
                v-for="agent in activeSubagents"
                :key="agent.role"
                :label="agent.role"
                :disabled="agent.required"
              >{{ agent.name }}</el-checkbox>
            </el-checkbox-group>
            <p v-for="agent in activeSubagents" :key="'d-' + agent.role" class="agent-duty">
              <b>{{ agent.name }}</b> {{ agent.description }}
            </p>

            <div class="plan-title">编排 Skill</div>
            <p class="hint">这是编排技能，不是工具底座里的 Skill 资源。勾选后，主 Agent 会根据当前对话上下文决定要不要调用。</p>
            <el-select v-model="selectedSkills" multiple filterable placeholder="选择本次要用的 Skill" style="width: 100%">
              <el-option v-for="skill in activeSkills" :key="skill.code" :label="skill.name" :value="skill.code" />
            </el-select>
            <el-button v-if="userStore.hasPermission('agent:invoke')" link type="primary" @click="showCustomSkill = true">添加 Skill</el-button>

            <div class="plan-title">MCP</div>
            <p class="hint">只列出工具底座里已注册的 MCP 连接。主 Agent 只能调用勾选的连接。</p>
            <el-select v-model="selectedMcps" multiple filterable placeholder="选择 MCP 连接" style="width: 100%">
              <el-option
                v-for="mcp in catalog.mcp_servers"
                :key="mcp.resource_id"
                :label="`${mcp.name} (${mcp.resource_id})`"
                :value="mcp.resource_id"
              />
            </el-select>

          </el-collapse-item></el-collapse>
          <el-button
            v-if="userStore.hasPermission('agent:invoke')"
            type="primary"
            :loading="creating"
            :disabled="!goalText.trim() || !plannerModelId"
            @click="createSession"
          >生成计划</el-button>
        </section>

        <template v-else>
          <div class="main-head">
            <div>
              <h3 class="sess-heading">{{ session.title || `会话 #${currentId}` }}</h3>
              <div class="head-meta">
                <StatusBadge :phase="productPhase" :text="productPhase === 'cancelled' ? '已停止' : ''" />
                <el-tag v-if="session.plan?.trial_run" size="small" type="info">试跑</el-tag>
                <el-tag v-else-if="session.plan?.ready" size="small">正式</el-tag>
                <span v-if="session.plan?.token_budget != null" class="hint">计划预算 {{ session.plan.token_budget }}</span>
                <span v-if="pollError" class="warn-inline">{{ pollError }}</span>
              </div>
            </div>
            <div class="head-actions">
              <el-button size="small" @click="drawerOpen = true">计划证据</el-button>
              <el-button v-if="canStopSession && userStore.hasPermission('agent:invoke')" size="small" :loading="controlLoading" @click="stopConversation">停止助手</el-button>
              <el-button v-if="canContinueSession && userStore.hasPermission('agent:invoke')" size="small" type="primary" :loading="controlLoading" @click="continueConversation">继续会话</el-button>
            </div>
          </div>

          <div v-if="sessionLoading && !session.id" class="hint">加载会话…</div>

          <div class="workflow-steps"><span :class="{ current: !session.task_id }">1 理解与规划</span><span :class="{ current: productPhase === 'awaiting_approval' || productPhase === 'approved' }">2 核对并确认</span><span :class="{ current: !!session.task_id && productPhase === 'running' }">3 执行与跟踪</span><span :class="{ current: productPhase === 'completed' }">4 结果与报告</span></div>
          <el-tabs v-model="workspaceTab" class="workspace-tabs">
          <el-tab-pane label="对话与计划" name="conversation">
          <section class="thread">
            <div class="thread-head">
              <div>
                <div class="plan-title">对话</div>
                <span class="hint">{{ displayedMessages.length }} 条消息 · {{ realtimeState }}</span>
              </div>
              <div class="reading-actions"><el-button v-if="userStore.hasPermission('agent:view')" link size="small" @click="focusReading = !focusReading">{{ focusReading ? '退出专注阅读' : '专注阅读' }}</el-button><el-button link size="small" native-type="button" @click="scrollThread(true)">回到最新</el-button></div>
            </div>
            <div ref="threadLog" class="thread-log" @scroll="onThreadScroll">
              <div v-if="!displayedMessages.length" class="thread-empty">还没有对话。生成计划后，补充说明会出现在这里。</div>
              <article v-for="m in displayedMessages" :key="m.id" class="msg" :class="m.role">
                <div class="msg-meta">
                  <b>{{ m.role === 'user' ? '你' : m.role === 'system' ? '系统' : '助手' }}</b>
                  <span v-if="replyAuthor(m)" class="agent-origin" :class="replyAuthor(m).kind" :title="replyAuthor(m).role">{{ replyAuthor(m).label }}</span>
                  <span v-if="m.created_at">{{ msgTime(m.created_at) }}</span>
                </div>
                <MarkdownMessage class="msg-body" :content="m.content" />
                <span v-if="m.delivery === 'sending'" class="delivery-note">正在发送…</span>
                <span v-if="m.delivery === 'failed'" class="delivery-note failed">发送未成功，请核对连接后重试。</span>
              </article>
              <article v-if="assistantBusy" class="msg assistant waiting-message" role="status" aria-live="polite">
                <div class="msg-meta"><b>评测助手</b><span>{{ waitingLabel }}</span></div>
                <span class="typing-dots" aria-label="正在等待助手更新"><i></i><i></i><i></i></span>
              </article>
            </div>
            <div class="composer">
              <el-input
                v-model="followUp"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="补充数据集、被测模型或打分工具。Ctrl+Enter 发送"
                @keydown.ctrl.enter="sendFollowUp"
              />
              <div class="composer-bar">
                <span class="hint">Ctrl+Enter 发送。核对当前计划后，可输入“确认执行”提交任务并持续跟进；“好的”等普通回复不会执行。</span>
                <el-button
                  v-if="userStore.hasPermission('agent:invoke')"
                  type="primary"
                  native-type="button"
                  :loading="runLoading"
                  :disabled="!followUp.trim() || !plannerModelId || assistantBusy"
                  @click="sendFollowUp"
                >发送</el-button>
              </div>
              <div class="continue-analysis"><el-button v-if="userStore.hasPermission('agent:invoke')" text :disabled="assistantBusy" @click="startRuntime">继续分析当前计划</el-button><span>沿用已保存的需求，重新检查资源和未完成事项；不会重复发送原需求或自动执行评测。</span></div>
            </div>
          </section>

          <!-- 计划摘要卡 -->
          <el-card v-if="session.plan" shadow="never" class="plan-card">
            <div class="plan-head">
              <div class="plan-title">计划摘要</div>
              <el-button size="small" native-type="button"  :disabled="assistantBusy || !!session.task_id || !userStore.hasPermission('agent:invoke')" @click="togglePlanEdit">{{ planEditing ? '收起' : '手动修改' }}</el-button>
            </div>
            <el-form v-if="planEditing" label-width="88px" size="small" class="plan-edit" @submit.prevent>
              <el-form-item label="目标">
                <el-input v-model="goalText" type="textarea" :rows="2" />
              </el-form-item>
              <el-form-item label="场景">
                <el-select v-model="clarifyForm.scene" filterable style="width: 100%">
                  <el-option v-for="item in sceneOptions" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="数据集">
                <ResourcePicker v-model="clarifyForm.dataset_id" kind="dataset" placeholder="搜索数据集" />
              </el-form-item>
              <el-form-item label="被测模型">
                <ResourcePicker v-model="clarifyForm.model_id" kind="model" placeholder="搜索被测模型" />
              </el-form-item>
              <el-form-item label="打分工具">
                <el-select v-model="clarifyForm.judge_resource_id" filterable style="width: 100%" placeholder="选择打分工具">
                  <el-option v-for="item in judgeOptions" :key="item.resource_id" :label="item.name" :value="item.resource_id" />
                </el-select>
              </el-form-item>
              <el-form-item label="预算">
                <el-input-number v-model="clarifyForm.token_budget" :min="0" controls-position="right" />
              </el-form-item>
              <el-form-item label="试跑模式">
                <el-switch v-model="clarifyForm.trial_run" /><p class="hint">试跑用于调通链路，放宽部分正式门禁；仍按所选数据版本执行并产生真实用量，不自动抽样。正式结论需关闭试跑后执行。</p>
              </el-form-item>
              <el-form-item label="子 Agent">
                <el-checkbox-group v-model="editRoles">
                  <el-checkbox
                    v-for="agent in activeSubagents"
                    :key="agent.role"
                    :label="agent.role"
                    :disabled="agent.required"
                  >{{ agent.name }}</el-checkbox>
                </el-checkbox-group>
                <div class="hint">监控分析和异常诊断始终启用，其余角色由主 Agent 按对话调用。</div>
              </el-form-item>
              <el-form-item label="Skill">
                <el-select v-model="editSkills" multiple filterable clearable placeholder="不选表示本次不启用" style="width: 100%">
                  <el-option v-for="skill in activeSkills" :key="skill.code" :label="skill.name" :value="skill.code" />
                </el-select>
              </el-form-item>
              <el-form-item label="MCP">
                <el-select v-model="editMcps" multiple filterable clearable placeholder="不选表示本次不启用" style="width: 100%">
                  <el-option
                    v-for="mcp in catalog.mcp_servers"
                    :key="mcp.resource_id"
                    :label="`${mcp.name} (${mcp.resource_id})`"
                    :value="mcp.resource_id"
                  />
                </el-select>
              </el-form-item>
              <el-button type="primary" native-type="button" :loading="clarifying" @click="clarify">保存到计划</el-button>
              <p class="hint">保存后计划摘要会改成这些值。若和已审批内容不一致，需要重新审批。</p>
            </el-form>
            <ul v-else class="plan-list">
              <li>目标：{{ session.plan.goal_spec?.objective || session.requirement }}</li>
              <li v-if="session.plan.dialogue_updated">这份计划已按后续对话更新过数据集、被测模型或打分工具。</li>
              <li>模板 {{ session.plan.template_code || '—' }} · 场景 {{ session.plan.scene || '—' }}</li>
              <li>
                数据
                <strong>{{ datasetLabel }}</strong>
                · 模型
                <strong>{{ modelLabel }}</strong>
              </li>
              <li>模式：{{ session.plan.trial_run ? '试跑' : '正式' }} · 计划预算 {{ session.plan.token_budget ?? 0 }}</li>
              <li>打分工具 {{ judgeLabel }}</li>
              <li v-if="session.plan.safety_config">
                安全协议：{{ session.plan.safety_config.set_type === 'explore' ? '探索集' : '固定集' }}，
                最多 {{ session.plan.safety_config.max_turns }} 轮，
                {{ session.plan.safety_config.adaptive ? '难度自适应' : '固定难度' }}，
                {{ session.plan.safety_config.turn_aggregation === 'worst' ? '最差轮次融合' : '均值融合' }}，
                {{ session.plan.safety_config.perspective_evaluation ? '启用情境对照' : '关闭情境对照' }}。
                规则占比 {{ Math.round(session.plan.safety_config.rule_weight * 100) }}%，
                裁判模型 {{ session.plan.safety_config.judge_model_id || '未选择' }}
                <el-collapse><el-collapse-item title="安全指标权重与冻结配置"><pre>{{ JSON.stringify(session.plan.safety_config, null, 2) }}</pre></el-collapse-item></el-collapse>
              </li>
              <li>子 Agent：{{ capabilityLabels.roles }}</li>
              <li>Skill：{{ capabilityLabels.skills }}</li>
              <li>MCP：{{ capabilityLabels.mcps }}</li>
            </ul>
            <el-collapse>
              <el-collapse-item title="技术详情（hash）" name="hash">
                <code>{{ session.plan.canonical_hash || '—' }}</code>
              </el-collapse-item>
            </el-collapse>
            <div v-if="session.plan.resource_gaps?.length" class="warn">
              资源缺口：
              <template v-for="(g, i) in session.plan.resource_gaps" :key="i">
                {{ g }}
                <router-link v-if="g.includes('模型')" class="link" to="/models">配置模型</router-link>
                <router-link v-else-if="g.includes('数据')" class="link" to="/datasets">配置数据集</router-link>
                <span v-if="i < session.plan.resource_gaps.length - 1">；</span>
              </template>
            </div>
            <div v-if="session.plan.validation_errors?.length" class="warn">校验：{{ session.plan.validation_errors.join('；') }}</div>
            <div class="cap-actions">
              <el-button v-if="userStore.hasPermission('agent:invoke')" size="small" native-type="button" @click="persistRecipe">沉淀经验</el-button>
            </div>
          </el-card>

          <!-- 待补充：动态澄清 -->
          <el-card v-if="showClarify" shadow="never" class="clarify-card">
            <div class="plan-title">{{ clarifyTitle }}</div>
            <div v-if="productPhase === 'budget_paused'" class="budget-box">
              <p class="clarify-q">
                这次运行已经用了 <strong>{{ liveRun?.tokens_used || 0 }}</strong> Token，限额是
                <strong>{{ liveRun?.token_budget || '未限额' }}</strong>，所以停在预算不足。
                点击「增加预算后继续」输入新预算。原执行记录保留；新一轮沿用已保存的上下文，不重复创建已有评测任务。
              </p>

            </div>
            <template v-if="productPhase !== 'budget_paused'">
            <p class="clarify-lead">每一项单独占一行。提交后计划摘要里的数字会变，旧审批作废，需要重新审批。</p>
            <div
              v-for="c in editableClarifications"
              :key="c.field + c.question"
              class="clarify-block"
            >
              <div class="clarify-label">{{ fieldLabel(c.field) }}</div>
              <p class="clarify-q">{{ c.question }}</p>
              <ResourcePicker
                v-if="c.field === 'dataset_id'"
                v-model="clarifyForm.dataset_id"
                kind="dataset"
                placeholder="搜索数据集"
              />
              <ResourcePicker
                v-else-if="c.field === 'model_id'"
                v-model="clarifyForm.model_id"
                kind="model"
                placeholder="搜索被测模型"
              />
              <el-input-number
                v-else-if="c.field === 'token_budget'"
                v-model="clarifyForm.token_budget"
                :min="0"
                controls-position="right"
              />
              <el-input
                v-else-if="c.field === 'objective'"
                v-model="goalText"
                type="textarea"
                :rows="2"
              />
            </div>
            <el-alert
              v-for="(g, i) in resourceGapTexts"
              :key="'gap-' + i"
              class="gap-alert"
              type="warning"
              :closable="false"
              show-icon
              :title="g"
            />
            <div class="clarify-block">
              <div class="clarify-label">试跑模式</div>
              <p class="clarify-q">用于调通数据、模型和裁判链路，放宽部分正式门禁；仍会真实调用模型并计费用量，不自动抽样。建议先选小题集，结果不能作为正式准入结论。</p>
              <el-switch v-model="clarifyForm.trial_run" />
            </div>
            <div v-if="!hasClarifyField('dataset_id')" class="clarify-block">
              <div class="clarify-label">数据集</div>
              <ResourcePicker v-model="clarifyForm.dataset_id" kind="dataset" placeholder="搜索数据集" />
            </div>
            <div v-if="!hasClarifyField('model_id')" class="clarify-block">
              <div class="clarify-label">被测模型</div>
              <ResourcePicker v-model="clarifyForm.model_id" kind="model" placeholder="搜索被测模型" />
            </div>
            </template>
          </el-card>

          <div class="action-dock">
            <el-button
              v-if="primaryAction"
              type="primary"
              :loading="primaryLoading"
              :disabled="primaryDisabled"
              @click="runPrimary"
            >{{ primaryAction.label }}</el-button>
            <el-button
              v-for="a in secondaryActions"
              :key="a.key"
              :loading="a.loading?.value"
              :disabled="a.disabled"
              @click="a.run"
            >{{ a.label }}</el-button>

            <span v-if="primaryHint" class="dock-hint">{{ primaryHint }}</span>
          </div>

          </el-tab-pane>
          <el-tab-pane label="执行明细" name="execution">
          <!-- 执行时间线 / 结果 -->
          <el-card v-if="run" shadow="never" class="run-card">
            <div class="plan-head">
              <div class="plan-title">每轮执行明细 · {{ purposeName(run.purpose) }} #{{ run.id }}</div>
              <StatusBadge :phase="runPhase" :text="runStatusText" />
            </div>
            <div class="turn-controls" v-if="userStore.hasPermission('agent:view')">
              <el-button :disabled="selectedTurnIndex <= 0" @click="moveTurn(-1)">上一轮</el-button>
              <el-select :model-value="run.id" @change="selectTurn" style="width: 300px">
                <el-option v-for="item in runHistory" :key="item.id" :value="item.id"
                  :label="`第 ${item.turn} 轮 · ${purposeName(item.purpose)} · ${item.status} · ${(item.input || '').slice(0, 24)}`" />
              </el-select>
              <el-button :disabled="selectedTurnIndex >= runHistory.length - 1" @click="moveTurn(1)">下一轮</el-button>
              <el-button :type="followLatest ? 'primary' : 'default'" plain @click="viewLatest">跟随最新</el-button>
            </div>
            <p v-if="!followLatest" class="hint">正在查看历史明细；切换明细不会停止后台执行。审批和执行操作针对当前计划。</p>
            <AgentExecutionDetails :items="delegations" :role-names="roleNames" />
            <p class="hint">
              模型决策 {{ run.rounds_used || 0 }} / {{ run.max_rounds }} 轮 <el-tooltip content="指这次执行中主 Agent 已调用模型作决策的次数／上限，不是聊天消息数，也不是评测样本数。0 表示尚未调用主模型；子 Agent 的模型轮次单独统计。"><span class="round-help">ⓘ 轮次说明</span></el-tooltip>
              · 已用 {{ run.tokens_used || 0 }} token
              · 限额 {{ run.token_budget || '未限额' }}
              <span v-if="run.tokens_usage_unknown"> · 用量未回报</span>
              <span v-if="eventsUpdatedAt"> · {{ eventsUpdatedAt }} 更新</span>
            </p>
            <p v-if="run.error_message" class="warn">{{ run.error_message }}</p>
            <p v-if="run.completion" class="hint">
              {{ run.completion.objective_verified ? '评测任务已完成，目标核验通过' :
                run.completion.kind === 'conversation_completed' ? '本轮对话已完成，尚未核验评测目标' :
                run.completion.kind === 'task_pending' ? '正在等待评测任务的实际执行结果' :
                run.completion.kind === 'evaluation_unverified' ? '任务已结束，评测目标尚未核验通过' : '等待执行或核验' }}
            </p>
            <el-timeline class="timeline">
              <el-timeline-item v-for="e in events" :key="`${run.id}-${e.seq}`" :timestamp="eventClock(e)" placement="top">
                <div class="event-title">{{ eventLabel(e.type) }}</div>
                <p class="event-detail">{{ eventDetail(e) }}</p>
                <el-collapse v-if="e.payload && Object.keys(e.payload).length">
                  <el-collapse-item title="原始数据" :name="String(e.seq)">
                    <pre class="payload">{{ formatPayload(e.payload) }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </el-timeline-item>
            </el-timeline>
          </el-card>

          <el-empty v-if="!run" description="助手开始分析后，执行明细会显示在这里。" />
          </el-tab-pane>
          <el-tab-pane label="报告与经验" name="reports">
          <el-card v-if="reportRevisions.length" shadow="never" class="result-card">
            <div class="plan-title">报告优化版本</div>
            <p class="hint">优化稿单独保存，原始报告及评分保留；发布和撤回须人工确认。</p>
            <el-collapse>
              <el-collapse-item v-for="item in reportRevisions" :key="item.id" :name="item.id" :title="`版本 #${item.id} · ${item.status} · 任务 #${item.task_id}`">
                <el-button v-if="userStore.hasPermission('agent:view')" @click="downloadRevision(item)">下载优化稿</el-button>
                <el-button v-if="item.status === 'draft' && userStore.hasPermission('agent:confirm')" type="primary" @click="actRevision(item, 'publish')">确认发布</el-button>
                <el-button v-if="item.status === 'published' && userStore.hasPermission('agent:confirm')" @click="actRevision(item, 'revert')">撤回优化稿</el-button>
                <MarkdownMessage :content="item.content" />
              </el-collapse-item>
            </el-collapse>
          </el-card>
          <el-card v-if="session.task_id && productPhase === 'completed'" shadow="never" class="result-card">
            <div class="plan-title">结果</div>
            <p>已关联任务 #{{ session.task_id }}（{{ session.plan?.trial_run ? '试跑' : '正式' }}）</p>
            <el-button type="primary" link @click="$router.push(`/tasks/${session.task_id}`)">查看任务 / 报告</el-button>
            <el-button v-if="userStore.hasPermission('agent:invoke')" link @click="persistRecipe">沉淀为可复用经验</el-button>
            <el-button link @click="startNew">基于此目标新建</el-button>
          </el-card>
          <el-empty v-if="!session.task_id" description="确认执行并完成评测后，在这里查看报告。" />
                          <el-table v-if="session.suggestions?.length" :data="session.suggestions" size="small" style="margin-top: 8px">
                  <el-table-column prop="action" label="建议" width="120" />
                  <el-table-column prop="reason" label="原因" />
                  <el-table-column width="100">
                    <template #default="{ row }">
                      <el-button
                        v-if="userStore.hasPermission('agent:confirm') && row.status === 'pending'"
                        link
                        type="primary"
                        @click="act(row, true)"
                      >采纳</el-button>
                    </template>
                  </el-table-column>
                </el-table>
          <el-collapse>              <el-collapse-item title="可复用经验（可选）" name="knowledge">
                <p class="empty-note">候选要通过审核后才进入知识库。生成计划和 Runtime 都不会把未审核条目塞进上下文，检索时也只按问题取最多 20 条已入库记录。</p>
                <el-form v-if="userStore.hasPermission('agent:invoke')" label-width="72px" size="small" class="cand-form">
                  <el-form-item label="标题"><el-input v-model="candidateForm.title" /></el-form-item>
                  <el-form-item label="分类">
                    <el-select v-model="candidateForm.category" style="width: 100%">
                      <el-option label="案例" value="case" />
                      <el-option label="模板" value="template" />
                      <el-option label="异常策略" value="exception" />
                      <el-option label="资源画像" value="profile" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="内容"><el-input v-model="candidateForm.content" type="textarea" :rows="2" /></el-form-item>
                  <el-button size="small" type="primary" :loading="savingCandidate" @click="submitCandidate">新增候选</el-button>
                </el-form>
                <div class="cand-tools">
                  <el-select v-model="candidateStatus" size="small" style="width: 120px" @change="loadCandidates">
                    <el-option label="待审核" value="pending" />
                    <el-option label="已通过" value="approved" />
                    <el-option label="已拒绝" value="rejected" />
                    <el-option label="全部" value="all" />
                  </el-select>
                  <el-button size="small" @click="loadCandidates">刷新</el-button>
                </div>
                <el-table :data="candidates" size="small" style="margin-top: 8px">
                  <el-table-column prop="id" label="#" width="50" />
                  <el-table-column prop="title" label="候选" show-overflow-tooltip />
                  <el-table-column prop="category" label="分类" width="90" />
                  <el-table-column prop="status" label="状态" width="80" />
                  <el-table-column width="130">
                    <template #default="{ row }">
                      <el-button
                        v-if="userStore.hasPermission('agent:confirm') && row.status === 'pending'"
                        link
                        type="primary"
                        @click="reviewCand(row, true)"
                      >通过</el-button>
                      <el-button
                        v-if="userStore.hasPermission('agent:invoke') && row.status !== 'approved'"
                        link
                        type="danger"
                        @click="removeCandidate(row)"
                      >删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-collapse-item></el-collapse>
          </el-tab-pane>
          </el-tabs>
        </template>
      </main>
    </div>

    <el-dialog v-model="showCustomAgent" :title="editingAgent ? '编辑子 Agent' : '添加子 Agent'" width="640px">
      <el-form label-width="120px">
        <el-form-item label="标识"><el-input v-model="customAgent.role" :disabled="editingAgent" placeholder="如 coverage_checker" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="customAgent.name" /></el-form-item>
        <el-form-item label="系统提示词"><el-input v-model="customAgent.system_prompt" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="最大迭代"><el-input-number v-model="customAgent.max_iterations" :min="1" :max="20" /></el-form-item>
        <el-form-item label="超时秒数"><el-input-number v-model="customAgent.timeout_seconds" :min="5" :max="600" /></el-form-item>
        <el-form-item label="执行动态"><span class="hint">跟随助手设置，通过实时事件展示执行过程；当前不逐字输出子 Agent 文本。</span></el-form-item>
        <el-form-item label="人工介入"><span class="hint">子 Agent 只提供分析；创建、恢复及补测必须经人员确认，不提供任意节点手动接管。</span></el-form-item>
        <el-form-item label="可调用工具">
          <el-checkbox-group v-model="customAgent.available_tools">
            <el-checkbox v-for="tool in mainToolOptions" :key="tool.name" :label="tool.name">{{ tool.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="可用 Skill">
          <el-select v-model="customAgent.skill_codes" multiple filterable clearable placeholder="这个子 Agent 可以调用的 Skill" style="width: 100%">
            <el-option v-for="skill in catalog.skills" :key="skill.code" :label="skill.name" :value="skill.code" :disabled="skill.enabled === false" />
          </el-select>
        </el-form-item>
        <el-form-item label="评测标尺">
          <el-input v-model="customAgent.evaluation_spec_text" type="textarea" :rows="2" placeholder='如 {"stages":["planning"],"trigger_keywords":["客服","售后"]}'  />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCustomAgent = false">取消</el-button>
        <el-button type="primary" :loading="savingCustom" @click="submitCustomAgent">保存</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="showCustomSkill" :title="editingSkill ? '编辑编排 Skill' : '添加编排 Skill'" width="520px">
      <el-form label-width="100px">
        <el-form-item label="标识"><el-input v-model="customSkill.code" :disabled="editingSkill" placeholder="如 weekly_report" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="customSkill.name" /></el-form-item>
        <el-form-item label="执行方式">
          <span>提示词模板</span>
        </el-form-item>
        <el-form-item label="提示词"><el-input v-model="customSkill.entry_point" type="textarea" :rows="4" placeholder="写给主 Agent 的提示约束" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCustomSkill = false">取消</el-button>
        <el-button type="primary" :loading="savingCustom" @click="submitCustomSkill">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="drawerOpen" title="计划与证据" size="420px">
      <pre v-if="session.plan" class="payload">{{ JSON.stringify(session.plan, null, 2) }}</pre>
      <el-table v-if="evidence.length" :data="evidence" size="small" style="margin-top: 12px">
        <el-table-column prop="role" label="来源" width="80" />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="ref" label="引用" show-overflow-tooltip />
      </el-table>
      <el-table v-if="session.approvals?.length" :data="session.approvals" size="small" style="margin-top: 12px">
        <el-table-column prop="id" label="#" width="50" />
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column prop="expires_at" label="过期" />
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentsApi, modelsApi, resourcesApi } from '@/api'
import { useUserStore } from '@/stores/user'
import StatusBadge from '@/components/StatusBadge.vue'
import ResourcePicker from '@/components/ResourcePicker.vue'
import AgentExecutionDetails from '@/components/AgentExecutionDetails.vue'
import MarkdownMessage from '@/components/MarkdownMessage.vue'
import { subscribeAgentEvents } from '@/utils/agentEvents'

const userStore = useUserStore()
const sessionQuery = ref('')
const filteredSessions = computed(() => sessions.value.filter(item => !sessionQuery.value.trim() || `${item.id} ${item.title || ''}`.toLowerCase().includes(sessionQuery.value.trim().toLowerCase())))
const settingsOpen = ref(false)
const workspaceTab = ref('conversation')
const pendingMessages = ref([])
const focusReading = ref(false)
const controlLoading = ref(false)
const realtimeState = ref('每2.5秒更新')
let streamController = null
let streamRetry = null
let streamRefresh = null
const displayedMessages = computed(() => {
  const stored = session.value.messages || []
  const ids = new Set(stored.map(item => item.payload?.client_message_id).filter(Boolean))
  return [...stored, ...pendingMessages.value.filter(item => !ids.has(item.client_message_id))]
})
const assistantBusy = computed(() => runLoading.value || !!liveRun.value && ['queued', 'running'].includes(liveRun.value.status) || liveRun.value?.status === 'waiting' && liveRun.value?.checkpoint?.phase === 'verify')
const waitingLabel = computed(() => liveRun.value?.checkpoint?.phase === 'verify' ? '任务执行中，关键节点会主动更新' : liveRun.value?.checkpoint?.phase === 'prepare' ? '正在核对资源并进行专项分析' : '正在分析，请稍候')
const canStopSession = computed(() => !!liveRun.value && ['queued','running','waiting'].includes(liveRun.value.status) && !liveRun.value.cancel_requested)
const canContinueSession = computed(() => !assistantBusy.value && ['stopped','cancelled','failed','paused_budget'].includes(session.value.display_status || liveRun.value?.status))
const sessionState = item => {
  const state = item.id === currentId.value ? session.value.display_status || item.display_status || item.status : item.display_status || item.status
  const states = {
    planning: ['规划中','blue'], tracking: ['跟踪中','blue'], running: ['执行中','blue'], queued: ['排队中','blue'],
    awaiting_approval: ['待确认','amber'], waiting_confirm: ['待确认','amber'], approved: ['待执行','amber'], needs_input: ['待补充','amber'],
    paused_budget: ['预算不足','amber'], completed: ['已完成','green'], success: ['已完成','green'], done: ['已完成','green'],
    failed: ['异常结束','red'], stopped: ['已停止','gray'], cancelled: ['已停止','gray'], stopping: ['正在停止','amber'],
  }
  const [label, tone] = states[state] || ['待处理','gray']
  return { label, tone }
}
async function stopConversation() {
  try { await ElMessageBox.confirm('停止助手的分析和跟踪？当前模型或工具请求会在节点结束后停止。已经提交的评测任务继续运行，可在任务详情单独管理，之后可以继续此会话。', '停止助手') } catch { return }
  controlLoading.value = true
  try { await agentsApi.stopSession(currentId.value); await loadSession(); await loadList() } finally { controlLoading.value = false }
}
async function continueConversation() {
  let budget = Number(session.value.plan?.token_budget || 0)
  if (liveRun.value?.status === 'paused_budget') {
    const floor = Math.max(Number(liveRun.value.tokens_used || 0), Number(liveRun.value.token_budget || 0))
    let answer
    try { answer = await ElMessageBox.prompt(`已用 ${liveRun.value.tokens_used} Token。输入大于 ${floor} 的新预算；原记录保留，并启动新的执行轮。`, '增加预算后继续', { inputValue: String(floor + 10000), inputValidator: value => Number.isInteger(Number(value)) && Number(value) > floor || `请输入大于 ${floor} 的整数` }) } catch { return }
    budget = Number(answer.value)
  }
  controlLoading.value = true
  followLatest.value = true
  try {
    await agentsApi.continueSession(currentId.value, { token_budget: budget })
    workspaceTab.value = 'conversation'
    await loadSession()
    await loadList()
    ElMessage.success('已继续会话；不会重复创建已有任务')
  } finally { controlLoading.value = false }
}
function stopEventStream() {
  streamController?.abort()
  streamController = null
  clearTimeout(streamRetry)
  clearTimeout(streamRefresh)
}
function startEventStream() {
  stopEventStream()
  if (!profileForm.value.supports_stream || !run.value?.id || ['success','failed','cancelled','paused_budget'].includes(run.value.status)) {
    realtimeState.value = '每2.5秒更新'
    return
  }
  const rid = run.value.id, sid = currentId.value, gen = sessionGen
  const controller = new AbortController()
  streamController = controller
  realtimeState.value = '正在连接实时动态'
  let eof = false
  subscribeAgentEvents({ runId: rid, afterSeq: eventCursor, token: userStore.token, signal: controller.signal,
    onConnected: () => { if (!controller.signal.aborted) realtimeState.value = '实时动态已连接' },
    onEvent: event => {
      if (controller.signal.aborted || gen !== sessionGen || run.value?.id !== rid) return
      if (event.type === 'run.eof') eof = true
      else mergeEvents([event], rid)
      clearTimeout(streamRefresh)
      streamRefresh = setTimeout(async () => {
        try {
          await refreshRun()
          const data = await agentsApi.getSession(sid)
          if (gen !== sessionGen || currentId.value !== sid) return
          session.value = data
          await Promise.all([loadRunHistory(sid,gen), loadRevisions(sid,gen)])
        } catch { /* periodic refresh remains active */ }
      }, 180)
    },
  }).catch(() => { if (!controller.signal.aborted) realtimeState.value = '连接中断，轮询更新' }).finally(() => {
    if (!controller.signal.aborted && !eof && streamController === controller) streamRetry = setTimeout(startEventStream, 1500)
  })
}
const route = useRoute()
const router = useRouter()

const budgetPanel = ref(['adv'])
const catalog = ref({ subagents: [], skills: [], mcp_servers: [] })
const recipes = ref([])
const selectedRoles = ref(['monitor', 'diagnose'])
const selectedSkills = ref([])
const selectedMcps = ref([])
const recipeId = ref(null)
const showCustomAgent = ref(false)
const showCustomSkill = ref(false)
const savingCustom = ref(false)
const mainToolOptions = [
  { name: 'get_resource_inventory', label: '读取授权资源清单' },
  { name: 'get_task_evidence', label: '读取任务及样本证据' },
  { name: 'search_knowledge', label: '检索经验知识' },
  { name: 'infer_dims', label: '推断场景' },
  { name: 'search_eval_resources', label: '检索评测资源' },
  { name: 'propose_resources', label: '写入计划' },
  { name: 'delegate_agent', label: '调用子 Agent' },
  { name: 'invoke_skill', label: '调用 Skill' },
  { name: 'call_mcp', label: '调用 MCP' },
  { name: 'get_task_status', label: '查询实际任务状态' },
  { name: 'request_task_execution', label: '请求审批执行评测' },
]
const emptyCustomAgent = () => ({
  role: '',
  name: '',
  system_prompt: '',
  max_iterations: 10,
  timeout_seconds: 120,
  supports_stream: false,
  human_in_the_loop: false,
  available_tools: ['search_knowledge'],
  skill_codes: [],
  evaluation_spec_text: '',
  enabled: true,
})
const customAgent = ref(emptyCustomAgent())
const profilePanel = ref([])
const catalogPanel = ref([])
const editingAgent = ref(false)
const editingSkill = ref(false)
const profileSaving = ref(false)
const profileForm = ref({
  system_prompt: '',
  model_name: '',
  temperature: 0,
  max_tokens: 0,
  available_tools: mainToolOptions.map((item) => item.name),
  max_iterations: 10,
  supports_stream: false,
  human_in_the_loop: true,
  evaluation_spec_text: '',
  timeout_seconds: 120,
})
const canEditProfile = computed(() => userStore.hasPermission('agent:invoke'))
const emptyCustomSkill = () => ({ code: '', name: '', execution_type: 'prompt_template', entry_point: '', enabled: true })
const customSkill = ref(emptyCustomSkill())
const activeSubagents = computed(() => (catalog.value.subagents || []).filter((item) => item.enabled !== false))
const activeSkills = computed(() => (catalog.value.skills || []).filter((item) => item.enabled !== false))
const railCollapsed = ref(false)
const drawerOpen = ref(false)
const goalText = ref('')
const followUp = ref('')
const planEditing = ref(false)
const editRoles = ref(['monitor', 'diagnose'])
const editSkills = ref([])
const editMcps = ref([])
const judgeOptions = ref([])
const threadLog = ref(null)
const threadStick = ref(true)
const sceneOptions = [
  { value: 'chat', label: '智能对话' },
  { value: 'table', label: '表格分析' },
  { value: 'writing', label: '文本写作' },
  { value: 'video', label: '视频生成' },
  { value: 'rag', label: 'RAG 检索增强生成' },
  { value: 'agent', label: '单智能体作业' },
  { value: 'multi_agent', label: '多智能体协同' },
  { value: 'code', label: '代码应用' },
  { value: 'embodied', label: '具身智能' },
  { value: 'industrial_sw', label: '工业软件辅助' },
  { value: 'science', label: '科学智算' },
]
const tokenBudget = ref(0)
const plannerModelId = ref(null)
const plannerModels = ref([])
const modelsLoadError = ref('')
const sessionsLoadError = ref('')
const creating = ref(false)
const clarifying = ref(false)
const approving = ref(false)
const confirming = ref(false)
const runLoading = ref(false)
const cancelLoading = ref(false)
const resumeLoading = ref(false)
const sessionLoading = ref(false)
const sessions = ref([])
const currentId = ref(null)
const session = ref({})
const approvalId = ref(null)
const run = ref(null)
const runHistory = ref([])
const reportRevisions = ref([])
const followLatest = ref(true)
let selectionGen = 0
const roleNames = computed(() => Object.fromEntries((catalog.value.subagents || []).map(item => [item.role, item.name])))
const selectedTurnIndex = computed(() => runHistory.value.findIndex(item => item.id === run.value?.id))
const liveRun = computed(() => {
  const id = session.value.active_run_id || session.value.last_run_id
  return run.value?.id === id ? run.value : runHistory.value.find(item => item.id === id)
})
const purposeName = value => ({ planning: '需求规划', dialogue: '对话', followup: '执行跟踪' }[value] || '对话')
async function loadRunHistory(sid = currentId.value, gen = sessionGen) {
  let page = 1, items = [], response
  do {
    response = await agentsApi.runs(sid, { page, page_size: 100 })
    items.push(...(response.items || []))
    page++
  } while (items.length < response.total)
  if (sid === currentId.value && gen === sessionGen) runHistory.value = items
}
async function selectTurn(id) {
  followLatest.value = false
  await loadRun(id)
}
async function moveTurn(offset) {
  const target = runHistory.value[selectedTurnIndex.value + offset]
  if (target) await selectTurn(target.id)
}
async function viewLatest() {
  followLatest.value = true
  await loadSession()
}
async function loadRevisions(sid = currentId.value, gen = sessionGen) {
  const data = await agentsApi.reportRevisions(sid)
  if (sid === currentId.value && gen === sessionGen) reportRevisions.value = data.items || []
}
async function actRevision(row, action) {
  await ElMessageBox.confirm(action === 'publish' ? '确认发布此优化稿？原始报告及评分仍保留。' : '确认撤回优化稿并恢复使用原始报告？', '人工确认')
  await (action === 'publish' ? agentsApi.publishReportRevision(row.id) : agentsApi.revertReportRevision(row.id))
  await loadRevisions()
  ElMessage.success(action === 'publish' ? '已发布优化稿' : '已撤回优化稿')
}
async function downloadRevision(row) {
  const blob = await agentsApi.downloadReportRevision(row.id)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `task-${row.task_id}-revision-${row.id}.md`
  link.click()
  URL.revokeObjectURL(url)
}
const events = ref([])
const eventsUpdatedAt = ref('')
const pollError = ref('')
const clarifyForm = ref({ dataset_id: null, model_id: null, token_budget: 0, trial_run: true, scene: '', judge_resource_id: '' })
const delegations = ref([])
const evidence = ref([])
const candidates = ref([])
const candidateStatus = ref('pending')
const savingCandidate = ref(false)
const candidateForm = ref({ title: '', content: '', category: 'case' })
const datasetLabel = ref('—')
const modelLabel = ref('—')

let sessionGen = 0
let eventCursor = 0
let seenEventSeq = new Set()
let pollTimer = null
const pollInFlight = ref(false)
let pendingConfirmInvocationId = ''

const dynamicClarifications = computed(() => session.value?.plan?.clarifications || [])
const editableClarifications = computed(() => dynamicClarifications.value.filter((c) => {
  if (c.field === 'resource') return false
  if (productPhase.value === 'budget_paused' && c.field === 'token_budget') return false
  return true
}))
const resourceGapTexts = computed(() => {
  const fromPlan = session.value?.plan?.resource_gaps || []
  const fromClarify = dynamicClarifications.value.filter((c) => c.field === 'resource').map((c) => c.question)
  return [...new Set([...fromPlan, ...fromClarify].filter(Boolean))]
})
const showClarify = computed(() => session.value.plan?.analysis_status !== 'pending' && ['needs_input', 'budget_paused'].includes(productPhase.value))
const clarifyTitle = computed(() => {
  if (productPhase.value === 'awaiting_approval') return '修改计划（提交后旧审批失效）'
  if (productPhase.value === 'budget_paused') return '预算已暂停，请调整后再提交'
  return '需要补充'
})

function hasClarifyField(field) {
  return dynamicClarifications.value.some((c) => c.field === field)
}

function fieldLabel(field) {
  return ({ dataset_id: '数据集', model_id: '被测模型', token_budget: '预算', objective: '目标', resource: '资源' }[field] || field)
}

function roleLabel(role) {
  return ({
    user: '你',
    main: '助手',
    system: '系统',
    monitor: '监控分析',
    diagnose: '异常诊断',
    plan_analyst: '方案分析',
    report_reviewer: '报告审校',
    param_advisor: '参数推荐',
  }[role] || role)
}

function replyAuthor(message) {
  const delegatedRole = String(message.tool_name || '').startsWith('delegate:') ? message.tool_name.slice(9) : ''
  if (!delegatedRole && ['user', 'system'].includes(message.role)) return null
  const role = delegatedRole || message.role
  if (['main', 'assistant'].includes(role)) return { kind: 'main-agent', role: 'main', label: '主 Agent' }
  const name = message.payload?.agent_name || catalog.value.subagents.find(agent => agent.role === role)?.name || roleLabel(role)
  return { kind: 'sub-agent', role, label: `子 Agent · ${name}` }
}

const judgeLabel = computed(() => {
  const id = session.value?.plan?.judge_resource_id
  if (!id) return '—'
  return judgeOptions.value.find((item) => item.resource_id === id)?.name || id
})

const runStatusText = computed(() => ({
  queued: '排队',
  running: '进行中',
  waiting: '等待',
  success: run.value?.completion?.objective_verified ? '目标已核验' : '本轮已结束',
  failed: '失败',
  cancelled: '已取消',
  paused_budget: '预算不足',
}[run.value?.status] || run.value?.status || ''))

function msgTime(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function scrollThread(force = false) {
  const el = threadLog.value
  if (!el || (!force && !threadStick.value)) return
  el.scrollTop = el.scrollHeight
}

function onThreadScroll() {
  const el = threadLog.value
  if (!el) return
  threadStick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 48
}

const capabilityLabels = computed(() => {
  const caps = session.value?.plan?.capabilities || {}
  const roles = (caps.subagent_roles || ['monitor', 'diagnose']).map((role) => (
    catalog.value.subagents.find((item) => item.role === role)?.name || role
  ))
  const skills = (caps.skill_codes || []).map((code) => (
    catalog.value.skills.find((item) => item.code === code)?.name || code
  ))
  const mcps = (caps.mcp_resource_ids || []).map((id) => (
    catalog.value.mcp_servers.find((item) => item.resource_id === id)?.name || id
  ))
  return {
    roles: roles.join('、') || '监控分析、异常诊断',
    skills: skills.join('、') || '未启用',
    mcps: mcps.join('、') || '未启用',
  }
})

function syncCapabilityEdits() {
  const caps = session.value?.plan?.capabilities || {}
  editRoles.value = [...(caps.subagent_roles?.length ? caps.subagent_roles : ['monitor', 'diagnose'])]
  editSkills.value = [...(caps.skill_codes || [])]
  editMcps.value = [...(caps.mcp_resource_ids || [])]
}

function togglePlanEdit() {
  planEditing.value = !planEditing.value
  if (planEditing.value) {
    syncCapabilityEdits()
    loadJudges().catch(() => {})
    if (!catalog.value.subagents?.length) loadCatalog().catch(() => {})
  }
}

async function loadJudges() {
  const res = await resourcesApi.judges()
  judgeOptions.value = res.items || res || []
}

function eventLabel(type) {
  if (type.startsWith('subagent.')) return `子 Agent · ${{ started: '开始专项任务', 'model.request': '模型输入', 'model.response': '模型响应', 'tool.started': '调用工具', 'tool.completed': '工具返回', 'tool.failed': '工具失败', completed: '专项完成', failed: '专项失败' }[type.slice(9)] || type.slice(9)}`
  const map = {
    'planning.started': '开始规划分析',
    'resources.discovered': '已读取授权资源',
    'llm.request': '主 Agent 模型输入',
    'task.tracking_started': '开始跟踪评测任务',
    'task.observed': '任务状态与结果更新',
    'task.heartbeat': '长任务定时跟进',
    'report.optimized': '优化报告草稿已保存',
    'collaboration.failed': '专项协作失败',
    'run.created': '已创建运行',
    'run.claimed': '已领取执行',
    'llm.select': '规划模型决策',
    'llm.select_none': '无需工具，准备回复',
    'tool.selected': '已选择工具',
    'tool.observed': '工具结果已写入',
    'tool.rejected': '工具参数被拒绝',
    'tool.failed': '工具执行失败',
    'llm.reply': '生成回复',
    'run.success': '运行成功',
    'run.failed': '运行失败',
    'run.cancelled': '已取消',
    'run.paused_budget': '预算暂停',
    'run.resume': '从检查点恢复',
    'run.waiting_approval': '等待用户审批',
    'run.waiting_task': '等待任务结果',
    'run.verified': '核验实际执行结果',
    'run.yielded': '等待继续执行',
  }
  return map[type] || type
}

function clipText(value, limit = 180) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

function toolLine(tool) {
  if (!tool || typeof tool !== 'object') return ''
  const name = tool.name || '工具'
  const args = tool.arguments && typeof tool.arguments === 'object' ? tool.arguments : {}
  const bits = Object.entries(args)
    .slice(0, 4)
    .map(([key, value]) => `${key}=${clipText(typeof value === 'string' ? value : JSON.stringify(value), 60)}`)
  return bits.length ? `${name}（${bits.join('，')}）` : name
}

function eventClock(event) {
  if (!event?.created_at) return `第 ${event?.seq || ''} 步`
  const date = new Date(event.created_at)
  if (Number.isNaN(date.getTime())) return `第 ${event.seq} 步`
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function eventDetail(event) {
  const payload = event?.payload || {}
  if (event.type.startsWith('subagent.')) return `${roleNames.value[payload.role] || payload.role || '子 Agent'} · 记录 #${payload.delegation_id || '—'}${payload.error ? ` · ${payload.error}` : ''}。详细输入和结果可在上方专项协作记录展开。`
  if (event.type === 'resources.discovered') return `已读取数据集 ${payload.datasets?.length || 0} 个、被测模型 ${payload.models?.length || 0} 个、工具 ${payload.tools?.length || 0} 个。`
  if (event.type === 'task.observed' || event.type === 'task.heartbeat') return `任务 #${payload.task_id}：${payload.status}，进度 ${payload.progress}%，通过 ${payload.success_count}，失败 ${payload.fail_count}。`
  if (event.type === 'report.optimized') return `优化稿 #${payload.revision_id} 已保存，等待人工审核。`
  if (event.type === 'llm.request') return '本轮主 Agent 的实际模型输入和工具范围已保存，可展开查看。'
  if (event.type === 'run.created') {
    return `开始向规划模型提问：${clipText(payload.message) || '（无问题文本）'}`
  }
  if (event.type === 'run.claimed') return '执行器已接过这次工具循环，开始按轮次调用规划模型。'
  if (event.type === 'llm.select') {
    const names = (payload.tools || []).filter(Boolean).join('、')
    const cost = payload.tokens == null ? '用量未回报' : `本步 ${payload.tokens} token`
    const latency = payload.latency_ms != null ? `，耗时 ${payload.latency_ms} ms` : ''
    if (payload.has_tool) return `规划模型决定调用 ${names || '工具'}。${cost}${latency}。`
    const preview = clipText(payload.preview)
    return `规划模型不再调用工具，准备直接回复。${cost}${latency}。${preview ? `草稿：${preview}` : ''}`
  }
  if (event.type === 'llm.select_none') return '这一轮没有工具调用，下一步会生成给用户看的回复。'
  if (event.type === 'tool.selected') {
    const lines = (payload.tools || []).map(toolLine).filter(Boolean)
    return lines.length ? `即将执行：${lines.join('；')}` : '已选定工具，参数见原始数据。'
  }
  if (event.type === 'tool.observed') {
    const result = payload.result || {}
    if (Array.isArray(result.updated)) return `${payload.tool || '工具'} 已写入计划：${result.updated.join('、')}。`
    if (result.datasets || result.models || result.judges) {
      return `${payload.tool || '检索'} 找到数据集 ${result.datasets?.length || 0} 个、被测模型 ${result.models?.length || 0} 个、打分工具 ${result.judges?.length || 0} 个。`
    }
    if (result.items) return `${payload.tool || '检索'} 命中 ${result.count ?? result.items.length} 条知识。`
    if (result.role) return `子 Agent ${result.role} 已返回分析，诊断不会直接执行恢复。`
    return `${payload.tool || '工具'} 已返回结果，展开原始数据可看完整内容。`
  }
  if (event.type === 'tool.rejected' || event.type === 'tool.failed') {
    return payload.error || '工具没有执行成功。'
  }
  if (event.type === 'llm.reply') return clipText(payload.reply, 280) || '已生成回复，内容在上方对话里。'
  if (event.type === 'run.success') return '工具循环结束。计划是否变化，以计划摘要为准。'
  if (event.type === 'run.failed') return payload.error || payload.detail || payload.error_code || '运行失败。'
  if (event.type === 'run.paused_budget') return `已用 ${payload.tokens_used ?? '未知'} token，达到本次限额，循环暂停。`
  if (event.type === 'run.cancelled') return '这次工具循环已取消，不会继续改计划。'
  if (event.type === 'run.resume') return `从「${payload.checkpoint_phase || '检查点'}」继续。`
  return '这一步没有额外说明。'
}

function formatPayload(p) {
  try {
    return JSON.stringify(p, null, 2)
  } catch {
    return String(p)
  }
}

function isApprovalValid(a, plan) {
  if (!a || a.status !== 'approved') return false
  if (a.consumed_task_id) return false
  if (plan?.canonical_hash && a.plan_hash && a.plan_hash !== plan.canonical_hash) return false
  if (a.expires_at) {
    const exp = Date.parse(a.expires_at)
    if (!Number.isNaN(exp) && exp < Date.now()) return false
  }
  return true
}

const activeApproval = computed(() => {
  const list = session.value?.approvals || []
  return list.find((a) => isApprovalValid(a, session.value?.plan)) || null
})

const TASK_RUNNING = ['draft', 'pending', 'queued', 'running', 'leasing']
const TASK_DONE = ['completed', 'success', 'done']

const productPhase = computed(() => {
  const s = session.value
  const r = liveRun.value
  if (!currentId.value || !s?.id) return 'idle'
  if (r?.status === 'paused_budget') return 'budget_paused'
  if (s.display_status === 'stopped' || r?.status === 'cancelled') return 'cancelled'
  if (r?.status === 'failed') return 'failed'
  if (s.plan?.analysis_status === 'pending') return 'planning'
  if (r?.checkpoint?.phase === 'await_approval' && !s.task_id) return activeApproval.value ? 'approved' : 'awaiting_approval'
  if (r && ['queued', 'running', 'waiting'].includes(r.status)) return 'running'
  if (s.task_id) {
    const ts = s.task_status || ''
    if (TASK_RUNNING.includes(ts)) return 'running'
    if (ts === 'failed' || ts === 'error') return 'failed'
    if (ts === 'cancelled' || ts === 'canceled') return 'cancelled'
    if (TASK_DONE.includes(ts) && s.report_status === 'available') return 'completed'
    if (TASK_DONE.includes(ts)) return 'report_pending'
    if (!ts) return 'running'
  }
  if (r?.status === 'success' && !s.task_id) {
    if (activeApproval.value) return 'approved'
    if (s.plan?.ready) return 'awaiting_approval'
    if (!s.plan?.ready || (s.plan?.clarifications || []).length) return 'needs_input'
    return 'needs_input'
  }
  if (activeApproval.value) return 'approved'
  if (s.plan?.ready && s.status === 'waiting_confirm') return 'awaiting_approval'
  if (s.status === 'approved') return 'approved'
  if (!s.plan?.ready || (s.plan?.clarifications || []).length) return 'needs_input'
  if (s.status === 'planning') return 'planning'
  return 'needs_input'
})

const runPhase = computed(() => {
  const st = run.value?.status
  if (st === 'paused_budget') return 'budget_paused'
  if (st === 'failed') return 'failed'
  if (st === 'success') return 'completed'
  if (['queued', 'running', 'waiting'].includes(st)) return 'running'
  return 'idle'
})

const primaryAction = computed(() => {
  if (!currentId.value) return null
  if (session.value.plan?.analysis_status === 'pending') return { key: 'noop', label: '正在检索资源并分析', disabled: true }
  const p = productPhase.value
  if (p === 'needs_input' || p === 'planning') return { key: 'clarify', label: '补充并更新计划' }
  if (p === 'awaiting_approval') return { key: 'approve', label: '审批计划' }
  if (p === 'approved') return { key: 'confirm', label: '确认并执行' }
  if (p === 'running') {
    return session.value?.task_id
      ? { key: 'view_task', label: '查看任务' }
      : { key: 'noop', label: '执行中', disabled: true }
  }
  if (p === 'failed') {
    if (!session.value?.task_id) return { key: 'continue', label: '继续会话' }
    if (liveRun.value && ['waiting', 'failed', 'queued'].includes(liveRun.value.status)) return { key: 'resume', label: '安全恢复' }
    if (session.value?.task_id) return { key: 'view_task', label: '查看失败任务' }
    return { key: 'clarify', label: '修改计划' }
  }
  if (p === 'cancelled') return { key: 'continue', label: '继续会话' }
  if (p === 'budget_paused') return { key: 'continue', label: '增加预算后继续' }
  if (p === 'report_pending') return { key: 'view_task', label: '查看任务' }
  if (p === 'completed' && session.value?.report_status === 'available') return { key: 'report', label: '查看报告' }
  if (p === 'completed' && session.value?.task_id) return { key: 'view_task', label: '查看任务' }
  if (p === 'completed') return { key: 'restart', label: '基于此目标新建' }
  return { key: 'clarify', label: '更新计划' }
})

const primaryLoading = computed(() => {
  const k = primaryAction.value?.key
  if (k === 'clarify' || k === 'raise_budget') return clarifying.value || runLoading.value
  if (k === 'approve') return approving.value
  if (k === 'confirm') return confirming.value
  if (k === 'continue') return controlLoading.value
  if (k === 'resume') return resumeLoading.value
  return false
})

const primaryDisabled = computed(() => {
  if (primaryAction.value?.disabled) return true
  if (primaryAction.value?.key === 'continue' && !userStore.hasPermission('agent:invoke')) return true
  const k = primaryAction.value?.key
  if (k === 'approve' && !userStore.hasPermission('agent:confirm')) return true
  if (k === 'confirm' && (!userStore.hasPermission('agent:confirm') || !activeApproval.value)) return true
  if ((k === 'clarify' || k === 'raise_budget') && !userStore.hasPermission('agent:invoke')) return true
  return false
})

const primaryHint = computed(() => {
  const p = productPhase.value
  if (session.value.plan?.analysis_status === 'pending') return '正在读取授权资源并调用规划子 Agent，可在下方展开已完成的专项记录。'
  if (p === 'approved' && !activeApproval.value) return '审批已失效，请重新签发后再执行。'
  if (p === 'budget_paused') return '新预算必须大于这次已用 token。确认后会重新启动一次运行，执行记录换成新的 run。'
  if (p === 'needs_input' || p === 'planning') return '补全缺项后点「补充并更新计划」。计划就绪后，主按钮会变成「审批计划」。'
  if (p === 'awaiting_approval') return '核对数据集、模型和预算后审批。若要改配置，点「保存计划修改」，旧审批会失效。'
  if (p === 'cancelled') return '助手已停止，点击「继续会话」沿用保存的上下文继续；已提交任务不会重复创建。'
  if (p === 'running' && !session.value?.task_id) return '工具循环还在执行，评测任务尚未创建。'
  if (primaryAction.value?.key === 'resume' && run.value && !['waiting', 'failed', 'queued'].includes(run.value.status)) {
    return '当前状态不可恢复'
  }
  return ''
})

const secondaryActions = computed(() => {
  const list = []
  const p = productPhase.value
  if (p === 'awaiting_approval' && userStore.hasPermission('agent:invoke')) {
    list.push({
      key: 'edit',
      label: '保存计划修改',
      disabled: clarifying.value,
      loading: clarifying,
      run: clarify,
    })
  }
  return list
})



async function runPrimary() {
  const k = primaryAction.value?.key
  if (k === 'clarify') return clarify()
  if (k === 'approve') return approve()
  if (k === 'confirm') return confirm(true)
  if (k === 'view_task' || k === 'report') {
    if (session.value.task_id) router.push(`/tasks/${session.value.task_id}`)
    return
  }
  if (k === 'continue' || k === 'resume') return continueConversation()
  if (k === 'restart') return startNew()

}

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function resetRunContext() {
  stopEventStream()
  stopPoll()
  run.value = null
  events.value = []
  eventCursor = 0
  seenEventSeq = new Set()
  eventsUpdatedAt.value = ''
  pollError.value = ''
  pollInFlight.value = false
}

function resetSessionSideState() {
  resetRunContext()
  runHistory.value = []
  reportRevisions.value = []
  followLatest.value = true
  selectionGen++
  session.value = {}
  pendingMessages.value = []
  approvalId.value = null
  delegations.value = []
  evidence.value = []
  pendingConfirmInvocationId = ''
  datasetLabel.value = '—'
  modelLabel.value = '—'
}

function loadFailureMessage(err, fallback) {
  const data = err?.response?.data
  const msg = data?.message ?? data?.detail ?? err?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

async function loadList() {
  sessionsLoadError.value = ''
  modelsLoadError.value = ''
  const [sSettled, modelsSettled] = await Promise.allSettled([
    agentsApi.sessions(),
    modelsApi.list({ page: 1, page_size: 100 }),
  ])
  if (sSettled.status === 'fulfilled') {
    sessions.value = sSettled.value.items || []
  } else {
    sessions.value = []
    sessionsLoadError.value = loadFailureMessage(sSettled.reason, '会话列表加载失败')
  }
  if (modelsSettled.status === 'fulfilled') {
    plannerModels.value = (modelsSettled.value.items || []).filter((m) => m.api_url)
  } else {
    plannerModels.value = []
    modelsLoadError.value = loadFailureMessage(modelsSettled.reason, '模型列表加载失败')
  }
}

async function loadCandidates() {
  const res = await agentsApi.knowledgeCandidates({ status: candidateStatus.value || undefined })
  candidates.value = res.items || []
}

async function submitCandidate() {
  if (!candidateForm.value.title.trim() || !candidateForm.value.content.trim()) {
    ElMessage.warning('请填写标题和内容')
    return
  }
  savingCandidate.value = true
  try {
    await agentsApi.addKnowledge({ ...candidateForm.value })
    candidateForm.value = { title: '', content: '', category: 'case' }
    candidateStatus.value = 'pending'
    await loadCandidates()
    ElMessage.success('已加入待审核候选')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '新增失败')
  } finally {
    savingCandidate.value = false
  }
}

async function removeCandidate(row) {
  try {
    await ElMessageBox.confirm(`删除候选「${row.title}」？已入库的知识不会一起删。`, '删除候选')
  } catch {
    return
  }
  await agentsApi.deleteKnowledge(row.id)
  ElMessage.success('已删除')
  await loadCandidates()
}

async function reviewCand(row, approveFlag) {
  await agentsApi.reviewKnowledge(row.id, { approve: approveFlag, ttl_days: 365 })
  ElMessage.success(approveFlag ? '已入库' : '已拒绝')
  await loadCandidates()
}

function startNew() {
  focusReading.value = false
  sessionGen++
  goalText.value = ''
  followUp.value = ''
  tokenBudget.value = 0
  recipeId.value = null
  selectedRoles.value = ['monitor','diagnose']
  selectedSkills.value = []
  selectedMcps.value = []
  clarifyForm.value = { dataset_id: null, model_id: null, token_budget: 0, trial_run: true, scene: '', judge_resource_id: '' }
  planEditing.value = false
  workspaceTab.value = 'conversation'
  pendingMessages.value = []
  currentId.value = null
  resetSessionSideState()
  router.replace({ path: '/agents', query: {} })
}

function selectSession(id) {
  if (currentId.value === id) return
  currentId.value = id
  router.replace({ path: '/agents', query: { session: String(id) } })
  loadSession()
}

async function resolveLabels(plan, sid, gen) {
  if (gen !== sessionGen || currentId.value !== sid) return
  datasetLabel.value = plan?.dataset_id ? `#${plan.dataset_id}` : '—'
  modelLabel.value = plan?.model_id ? `#${plan.model_id}` : '—'
  try {
    if (plan?.dataset_id) {
      const { datasetsApi } = await import('@/api')
      const d = await datasetsApi.get(plan.dataset_id)
      if (gen !== sessionGen || currentId.value !== sid) return
      datasetLabel.value = d.name || datasetLabel.value
    }
  } catch { /* */ }
  try {
    if (plan?.model_id) {
      const m = await modelsApi.get(plan.model_id)
      if (gen !== sessionGen || currentId.value !== sid) return
      modelLabel.value = m.name || modelLabel.value
    }
  } catch { /* */ }
}

function pageScroller() {
  return document.querySelector('.main')
}

function holdPageScroll() {
  const scroller = pageScroller()
  const top = scroller ? scroller.scrollTop : 0
  const restore = () => {
    if (scroller) scroller.scrollTop = top
  }
  nextTick(restore)
  requestAnimationFrame(restore)
  setTimeout(restore, 80)
}

function rememberPageClick(event) {
  if (!event.target.closest('button, .el-button')) return
  holdPageScroll()
}

async function loadSession() {
  const sid = currentId.value
  if (!sid) {
    resetSessionSideState()
    return
  }
  const gen = ++sessionGen
  const sameSession = session.value?.id === sid
  const scroller = pageScroller()
  const savedScroll = scroller ? scroller.scrollTop : 0
  if (!sameSession) resetSessionSideState()
  sessionLoading.value = true
  try {
    const data = await agentsApi.getSession(sid)
    if (gen !== sessionGen || currentId.value !== sid) return
    session.value = data
    if (data.planner_model_id) plannerModelId.value = data.planner_model_id
    goalText.value = data.requirement || goalText.value
    if (data.plan?.goal_spec?.objective) goalText.value = data.plan.goal_spec.objective
    clarifyForm.value = {
      dataset_id: data.plan?.dataset_id || null,
      model_id: data.plan?.model_id || null,
      token_budget: data.plan?.token_budget || 0,
      trial_run: typeof data.plan?.trial_run === 'boolean' ? data.plan.trial_run : true,
      scene: data.plan?.scene || '',
      judge_resource_id: data.plan?.judge_resource_id || '',
    }
    tokenBudget.value = data.plan?.token_budget || tokenBudget.value
    const valid = (data.approvals || []).find((a) => isApprovalValid(a, data.plan))
    approvalId.value = valid?.id || null
    await resolveLabels(data.plan, sid, gen)
    if (gen !== sessionGen || currentId.value !== sid) return
    await Promise.all([loadRunHistory(sid, gen), loadRevisions(sid, gen)])
    const runId = !followLatest.value && sameSession && run.value?.id ? run.value.id : data.active_run_id || data.last_run_id
    if (runId) await loadRun(runId, sid, gen)
    if (!plannerModelId.value && run.value?.planner_model_id) plannerModelId.value = run.value.planner_model_id
    if (gen === sessionGen && currentId.value === sid) applyPausedBudgetDefault()
    if (sameSession) {
      nextTick(() => {
        if (scroller) scroller.scrollTop = savedScroll
        scrollThread(threadStick.value)
      })
    } else {
      threadStick.value = true
      nextTick(() => scrollThread(true))
    }
  } catch (e) {
    if (gen === sessionGen) ElMessage.error(e?.response?.data?.detail || e?.message || '加载会话失败')
  } finally {
    if (gen === sessionGen) sessionLoading.value = false
  }
}

async function loadDelegations(sid = currentId.value, gen = sessionGen) {
  if (!sid) return
  const rid = run.value?.id
  const res = await agentsApi.delegations(sid, rid ? { run_id: rid } : {})
  if (gen !== sessionGen || currentId.value !== sid || run.value?.id !== rid) return
  delegations.value = res.items || []
  evidence.value = res.evidence || []
}

async function loadCatalog() {
  try {
    const [cat, recipeRes] = await Promise.all([agentsApi.catalog(), agentsApi.recipes()])
    catalog.value = cat
    recipes.value = recipeRes.items || []
    const required = (cat.subagents || []).filter((item) => item.required).map((item) => item.role)
    selectedRoles.value = Array.from(new Set([...required, ...selectedRoles.value]))
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '能力目录加载失败')
  }
}

function applyRecipe(id) {
  const recipe = recipes.value.find((item) => item.id === id)
  if (!recipe) return
  const snap = recipe.snapshot || {}
  if (recipe.requirement) goalText.value = recipe.requirement
  if (snap.token_budget != null) tokenBudget.value = snap.token_budget
  const bound = snap.capabilities || {}
  if (bound.subagent_roles?.length) selectedRoles.value = bound.subagent_roles
  selectedSkills.value = bound.skill_codes || []
  selectedMcps.value = bound.mcp_resource_ids || []
}

async function persistRecipe() {
  if (!currentId.value) return
  const row = await agentsApi.saveRecipe(currentId.value)
  ElMessage.success('已沉淀，下次可直接复用')
  await loadCatalog()
  recipeId.value = row.id
}

function toolLabels(names) {
  const map = Object.fromEntries(mainToolOptions.map((item) => [item.name, item.label]))
  const list = (names || []).map((name) => map[name] || name)
  return list.length ? list.join('、') : '未配置'
}

function skillLabels(codes) {
  const map = Object.fromEntries((catalog.value.skills || []).map((item) => [item.code, item.name]))
  const list = (codes || []).map((code) => map[code] || code)
  return list.length ? list.join('、') : '未配置'
}

function executionLabel(kind) {
  return { prompt_template: '提示词模板', workflow: '工作流', agent: '转交子 Agent', code: '代码' }[kind] || kind || ''
}

function agentStatus(row) {
  if (row.enabled === false) return '已停用'
  return row.builtin ? '内置' : '自定义'
}

function agentPayload(source, enabled) {
  let evaluationSpec = null
  const specText = (source.evaluation_spec_text || '').trim()
  if (specText) {
    evaluationSpec = JSON.parse(specText)
    if (!evaluationSpec || typeof evaluationSpec !== 'object' || Array.isArray(evaluationSpec)) {
      throw new Error('评测标尺须是 JSON 对象')
    }
  } else if (source.evaluation_spec && typeof source.evaluation_spec === 'object') {
    evaluationSpec = source.evaluation_spec
  }
  return {
    role: source.role,
    name: source.name,
    description: source.description || '',
    system_prompt: source.system_prompt || '',
    max_iterations: source.max_iterations || 10,
    timeout_seconds: source.timeout_seconds || 120,
    supports_stream: !!source.supports_stream,
    human_in_the_loop: !!source.human_in_the_loop,
    available_tools: source.available_tools || [],
    skill_codes: source.skill_codes || [],
    evaluation_spec: evaluationSpec,
    enabled: enabled != null ? enabled : source.enabled !== false,
  }
}

function openAgentEditor(row) {
  editingAgent.value = !!row
  if (!row) {
    customAgent.value = emptyCustomAgent()
  } else {
    customAgent.value = {
      role: row.role,
      name: row.name,
      description: row.description || '',
      system_prompt: row.system_prompt || '',
      max_iterations: row.max_iterations || 10,
      timeout_seconds: row.timeout_seconds || 120,
      supports_stream: !!row.supports_stream,
      human_in_the_loop: !!row.human_in_the_loop,
      available_tools: [...(row.available_tools || [])],
      skill_codes: [...(row.skill_codes || [])],
      evaluation_spec_text: row.evaluation_spec ? JSON.stringify(row.evaluation_spec, null, 2) : '',
      enabled: row.enabled !== false,
    }
  }
  showCustomAgent.value = true
}

function openSkillEditor(row) {
  editingSkill.value = !!row
  customSkill.value = row
    ? {
      code: row.code,
      name: row.name,
      description: row.description || '',
      execution_type: 'prompt_template',
      entry_point: row.entry_point || '',
      enabled: row.enabled !== false,
    }
    : emptyCustomSkill()
  showCustomSkill.value = true
}

async function submitCustomAgent() {
  savingCustom.value = true
  try {
    const payload = agentPayload(customAgent.value)
    const wasEdit = editingAgent.value
    if (wasEdit) await agentsApi.updateDefinition(payload.role, payload)
    else await agentsApi.createDefinition(payload)
    showCustomAgent.value = false
    customAgent.value = emptyCustomAgent()
    editingAgent.value = false
    await loadCatalog()
    ElMessage.success(wasEdit ? '子 Agent 已更新' : '子 Agent 已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    savingCustom.value = false
  }
}

async function removeAgent(row) {
  try {
    await ElMessageBox.confirm(row.builtin ? `停用「${row.name}」后，新建评测不能再选它。` : `删除子 Agent「${row.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  await agentsApi.deleteDefinition(row.role)
  await loadCatalog()
  ElMessage.success(row.builtin ? '已停用' : '已删除')
}

async function restoreAgent(row) {
  await agentsApi.updateDefinition(row.role, agentPayload({
    ...row,
    evaluation_spec_text: row.evaluation_spec ? JSON.stringify(row.evaluation_spec) : '',
  }, true))
  await loadCatalog()
  ElMessage.success('已恢复')
}

async function submitCustomSkill() {
  savingCustom.value = true
  try {
    const payload = { ...customSkill.value, execution_type: 'prompt_template' }
    const created = editingSkill.value
      ? await agentsApi.updateSkill(payload.code, payload)
      : await agentsApi.createSkill(payload)
    showCustomSkill.value = false
    customSkill.value = emptyCustomSkill()
    const wasEdit = editingSkill.value
    editingSkill.value = false
    await loadCatalog()
    if (!wasEdit && created.code) selectedSkills.value = Array.from(new Set([...selectedSkills.value, created.code]))
    ElMessage.success(wasEdit ? 'Skill 已更新' : 'Skill 已加入本次可选列表')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    savingCustom.value = false
  }
}

async function removeSkill(row) {
  try {
    await ElMessageBox.confirm(row.builtin ? `停用编排 Skill「${row.name}」？` : `删除编排 Skill「${row.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  await agentsApi.deleteSkill(row.code)
  await loadCatalog()
  ElMessage.success(row.builtin ? '已停用' : '已删除')
}

async function restoreSkill(row) {
  await agentsApi.updateSkill(row.code, { ...row, enabled: true })
  await loadCatalog()
  ElMessage.success('已恢复')
}

async function createSession() {
  if (!plannerModelId.value) {
    ElMessage.warning('请选择规划模型')
    return
  }
  creating.value = true
  try {
    const created = await agentsApi.createSession({
      requirement: goalText.value.trim(),
      objective: goalText.value.trim(),
      token_budget: tokenBudget.value || 0,
      skill_codes: selectedSkills.value,
      mcp_resource_ids: selectedMcps.value,
      subagent_roles: selectedRoles.value,
      recipe_id: recipeId.value || undefined,
      planner_model_id: plannerModelId.value,
    })
    ElMessage.success(created.plan?.analysis_status === 'pending' ? '正在检索资源并调用规划子 Agent' : created.plan?.ready ? '计划已就绪，可审批' : '需要补充信息')
    await loadList()
    currentId.value = created.id
    router.replace({ path: '/agents', query: { session: String(created.id) } })
    await loadSession()
  } finally {
    creating.value = false
  }
}

async function clarify() {
  if (!currentId.value) return
  clarifying.value = true
  try {
    const payload = {
      objective: goalText.value || session.value.requirement,
      trial_run: clarifyForm.value.trial_run,
      token_budget: clarifyForm.value.token_budget,
      scene: clarifyForm.value.scene || undefined,
      judge_resource_id: clarifyForm.value.judge_resource_id || undefined,
    }
    if (clarifyForm.value.dataset_id) payload.dataset_id = clarifyForm.value.dataset_id
    if (clarifyForm.value.model_id) payload.model_id = clarifyForm.value.model_id
    const savingCapabilities = planEditing.value
    await agentsApi.clarify(currentId.value, payload)
    if (savingCapabilities) {
      await agentsApi.updateCapabilities(currentId.value, {
        subagent_roles: editRoles.value,
        skill_codes: editSkills.value,
        mcp_resource_ids: editMcps.value,
      })
    }
    planEditing.value = false
    pendingConfirmInvocationId = ''
    const prev = Number(session.value?.plan?.token_budget || 0)
    const next = Number(clarifyForm.value.token_budget || 0)
    ElMessage.success(
      prev !== next
        ? `计划预算已从 ${prev} 改为 ${next}。配置已变，之前的审批作废，需要重新审批后才能执行评测任务。`
        : '计划已按当前选项重新保存。配置若有变化，之前的审批会作废。',
    )
    await loadSession()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '澄清失败')
  } finally {
    clarifying.value = false
  }
}

async function approve() {
  if (!currentId.value) return
  approving.value = true
  try {
    const res = await agentsApi.approve(currentId.value, { ttl_minutes: 30 })
    approvalId.value = res.approval?.id
    ElMessage.success(`已签发审批 #${approvalId.value}`)
    await loadSession()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '审批失败')
  } finally {
    approving.value = false
  }
}

async function confirm(execute) {
  if (!currentId.value || !activeApproval.value) {
    ElMessage.warning('需要有效审批')
    return
  }
  confirming.value = true
  try {
    if (!pendingConfirmInvocationId) pendingConfirmInvocationId = `ui-${currentId.value}-${Date.now()}`
    const res = await agentsApi.confirm(currentId.value, {
      execute,
      approval_id: activeApproval.value.id,
      client_invocation_id: pendingConfirmInvocationId,
    })
    pendingConfirmInvocationId = ''
    ElMessage.success(res.idempotent ? `幂等返回任务 #${res.task_id}` : `已创建任务 #${res.task_id}`)
    await loadSession()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '确认失败')
  } finally {
    confirming.value = false
  }
}

async function act(row, accepted) {
  await agentsApi.actSuggestion(row.id, { accepted })
  await loadSession()
}

function mergeEvents(items, rid) {
  if (!items?.length) return
  for (const e of items) {
    const key = `${rid}:${e.seq}`
    if (seenEventSeq.has(key)) continue
    seenEventSeq.add(key)
    events.value.push(e)
    eventCursor = Math.max(eventCursor, e.seq)
  }
  eventsUpdatedAt.value = new Date().toLocaleTimeString()
}

async function loadRun(rid, sid = currentId.value, gen = sessionGen) {
  const selection = ++selectionGen
  resetRunContext()
  const data = await agentsApi.getRun(rid)
  if (gen !== sessionGen || currentId.value !== sid || selection !== selectionGen) return
  run.value = data
  const res = await agentsApi.runEvents(rid, { after_seq: 0 })
  if (gen !== sessionGen || currentId.value !== sid || selection !== selectionGen) return
  events.value = []
  seenEventSeq = new Set()
  eventCursor = 0
  mergeEvents(res.items || [], rid)
  await loadDelegations(sid, gen)
  startEventStream()
  schedulePoll()
}

async function refreshRun() {
  const rid = run.value?.id
  const sid = currentId.value
  const gen = sessionGen
  if (!rid || pollInFlight.value) return
  pollInFlight.value = true
  try {
    const data = await agentsApi.getRun(rid)
    if (gen !== sessionGen || currentId.value !== sid || run.value?.id !== rid) return
    run.value = data
    const res = await agentsApi.runEvents(rid, { after_seq: eventCursor })
    if (gen !== sessionGen || run.value?.id !== rid) return
    mergeEvents(res.items || [], rid)
    await loadDelegations(sid, gen)
    pollError.value = ''
  } catch (e) {
    if (gen === sessionGen) pollError.value = e?.response?.data?.detail || e?.message || '刷新失败'
  } finally {
    pollInFlight.value = false
  }
}

function schedulePoll() {
  stopPoll()
  const sid = currentId.value
  const gen = sessionGen
  const tick = async () => {
    if (sid !== currentId.value || gen !== sessionGen) return
    try {
      await refreshRun()
      const data = await agentsApi.getSession(sid)
      if (sid !== currentId.value || gen !== sessionGen) return
      const finishedPlanning = session.value.plan?.analysis_status === 'pending' && data.plan?.analysis_status !== 'pending'
      session.value = data
      await Promise.all([loadRunHistory(sid, gen), loadRevisions(sid, gen)])
      if (finishedPlanning) { await loadSession(); return }
      const latest = data.active_run_id || data.last_run_id
      if (followLatest.value && latest && latest !== run.value?.id) { await loadRun(latest, sid, gen); return }
      pollError.value = ''
    } catch (e) {
      if (gen === sessionGen) pollError.value = loadFailureMessage(e, '刷新执行明细失败')
    }
    if (gen !== sessionGen) return
    const active = liveRun.value && ['queued', 'running', 'waiting'].includes(liveRun.value.status)
    if (active || TASK_RUNNING.includes(session.value.task_status)) pollTimer = setTimeout(tick, 2500)
  }
  pollTimer = setTimeout(tick, 2000)
}

function applyPausedBudgetDefault() {
  if (run.value?.status !== 'paused_budget') return
  const used = Number(run.value.tokens_used || 0)
  const cap = Number(run.value.token_budget || 0)
  const floor = Math.max(used, cap)
  if (Number(clarifyForm.value.token_budget || 0) <= floor) {
    clarifyForm.value.token_budget = floor + 2000
  }
  if (!plannerModelId.value && run.value.planner_model_id) {
    plannerModelId.value = run.value.planner_model_id
  }
}

function startRuntime() {
  return launchRuntime({ message: '请沿用当前需求和计划，检查尚未完成的分析与资源缺口，给出下一步建议；不要重述原需求，不自动执行任务。' }).catch(() => {})
}
async function sendFollowUp() {
  const text = followUp.value.trim()
  if (!text || runLoading.value || assistantBusy.value) return
  if (!plannerModelId.value) { ElMessage.warning('请选择已配置的规划模型'); return }
  const sid = currentId.value
  const local = { id: `pending-${crypto.randomUUID()}`, client_message_id: crypto.randomUUID(), role: 'user', content: text, created_at: new Date().toISOString(), delivery: 'sending' }
  pendingMessages.value.push(local)
  followUp.value = ''
  nextTick(() => scrollThread(true))
  try {
    if (['确认执行', '确认当前计划并执行', '按当前计划执行', '确认提交并执行'].includes(text.replace(/[。！!.]+$/, ''))) {
      if (!userStore.hasPermission('agent:confirm')) throw new Error('当前账号没有审批执行权限')
      if (!session.value.plan?.ready || session.value.plan?.analysis_status === 'pending') throw new Error('计划尚未就绪，请先补充信息并等待分析完成')
      runLoading.value = true
      const result = await agentsApi.confirm(sid, { execute: true, expected_plan_hash: session.value.plan.canonical_hash, confirmation_message: text, client_message_id: local.client_message_id, client_invocation_id: `chat-${local.client_message_id}` })
      if (result.idempotent && sid === currentId.value) pendingMessages.value = pendingMessages.value.filter(item => item.id !== local.id)
      followLatest.value = true
      if (sid === currentId.value) { await loadSession(); await loadList(); ElMessage.success('已按对话确认提交任务，助手将持续跟进') }
    } else await launchRuntime({ message: text, clientMessageId: local.client_message_id })
  } catch (error) {
    if (sid === currentId.value) {
      const pending = pendingMessages.value.find(item => item.id === local.id)
      if (pending) pending.delivery = 'failed'
    }
    ElMessage.error(error?.response?.data?.detail || error?.message || '发送失败')
  } finally {
    runLoading.value = false
  }
}

async function launchRuntime({ quiet = false, budget = null, message = '', clientMessageId = '' } = {}) {
  if (!currentId.value || !plannerModelId.value) {
    ElMessage.warning('请选择已配置 api_url 的规划模型')
    return
  }
  runLoading.value = true
  followLatest.value = true
  const sid = currentId.value
  const gen = sessionGen
  const nextBudget = budget == null ? Number(clarifyForm.value.token_budget || tokenBudget.value || 0) : Number(budget)
  const text = String(message || goalText.value || session.value.requirement || '').trim()
  try {
    const data = await agentsApi.startRun(sid, {
      message: text,
      client_message_id: clientMessageId,
      provider: 'live',
      planner_model_id: plannerModelId.value,
      token_budget: nextBudget,
      sync: false,
      max_rounds: Number(profileForm.value.max_iterations) || 10,
    })
    if (gen !== sessionGen || currentId.value !== sid) return
    run.value = data
    events.value = []
    seenEventSeq = new Set()
    eventCursor = 0
    await refreshRun()
    await loadSession()
    if (!quiet) ElMessage.success(`已启动运行，状态 ${run.value?.status || data.status}，预算 ${nextBudget || '未限额'}`)
  } catch (e) {
    if (!quiet) ElMessage.error(e?.response?.data?.detail || e?.message || 'Runtime 失败')
    throw e
  } finally {
    runLoading.value = false
  }
}

watch(() => profileForm.value.supports_stream, () => { if (run.value?.id) startEventStream() })

watch(
  () => route.query.session,
  (v) => {
    const id = v ? Number(v) : null
    if (id && id !== currentId.value) {
      currentId.value = id
      loadSession()
    }
    if (!v && currentId.value) {
      // keep local selection unless explicitly cleared via startNew
    }
  },
)

watch(
  () => (session.value.messages || []).map((item) => item.id).join(','),
  () => nextTick(() => scrollThread(false)),
)

function applyProfile(data) {
  const cfg = data?.model_config || {}
  profileForm.value = {
    system_prompt: data?.system_prompt || '',
    model_name: cfg.model_name || '',
    temperature: cfg.temperature ?? 0,
    max_tokens: cfg.max_tokens || 0,
    available_tools: data?.available_tools?.length ? data.available_tools : mainToolOptions.map((item) => item.name),
    max_iterations: data?.max_iterations || 10,
    supports_stream: !!data?.supports_stream,
    human_in_the_loop: data?.human_in_the_loop !== false,
    evaluation_spec_text: data?.evaluation_spec ? JSON.stringify(data.evaluation_spec, null, 2) : '',
    timeout_seconds: data?.timeout_seconds || 120,
  }
}

async function loadProfile() {
  applyProfile(await agentsApi.profile())
}

async function saveProfile() {
  let spec = null
  const raw = (profileForm.value.evaluation_spec_text || '').trim()
  if (raw) {
    try {
      spec = JSON.parse(raw)
    } catch {
      ElMessage.error('评测标尺须是 JSON 对象')
      return
    }
    if (!spec || typeof spec !== 'object' || Array.isArray(spec)) {
      ElMessage.error('评测标尺须是 JSON 对象')
      return
    }
  }
  profileSaving.value = true
  try {
    const saved = await agentsApi.saveProfile({
      system_prompt: profileForm.value.system_prompt,
      model_config: {
        model_name: profileForm.value.model_name,
        temperature: Number(profileForm.value.temperature) || 0,
        max_tokens: Number(profileForm.value.max_tokens) || 0,
      },
      available_tools: profileForm.value.available_tools,
      max_iterations: Number(profileForm.value.max_iterations) || 10,
      supports_stream: profileForm.value.supports_stream,
      human_in_the_loop: true,
      evaluation_spec: spec,
      timeout_seconds: Number(profileForm.value.timeout_seconds) || 120,
    })
    applyProfile(saved)
    ElMessage.success('主 Agent 配置已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    profileSaving.value = false
  }
}

onMounted(async () => {
  document.addEventListener('click', rememberPageClick, true)
  loadJudges().catch(() => {})
  loadProfile().catch(() => {})
  await loadCatalog()
  await loadList()
  const q = route.query.session
  if (q) {
    currentId.value = Number(q)
    await loadSession()
  }
  if (window.innerWidth < 1100) railCollapsed.value = true
})

onUnmounted(() => {
  stopEventStream()
  document.removeEventListener('click', rememberPageClick, true)
  sessionGen += 1
  stopPoll()
})
</script>

<style scoped>
.profile-form { margin-top: 26px; }
.reading-actions { display: flex; gap: 14px; align-items: center; }
.focus-reading .session-rail { display: none; }
.focus-reading .thread { height: max(780px, calc(100vh - 210px)); }
.agents-wb { --rail-w: 260px; }
.profile-card { margin-bottom: 16px; }
.skill-head { margin-top: 18px; }
.profile-more { margin-top: 12px; }
.profile-form .hint { margin-left: 8px; }
.wb-layout { display: flex; gap: 16px; align-items: flex-start; min-height: 60vh; }
.session-rail {
  position: sticky;
  top: 12px;
  width: var(--rail-w);
  max-height: calc(100vh - 120px);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: var(--radius-md, 10px);
  padding: 12px;
}
.rail-scroll { overflow-y: auto; min-height: 0; flex: 1; }
.session-rail.collapsed { width: 72px; }
.rail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
.new-btn { width: 100%; margin-bottom: 8px; }
.rail-empty { font-size: 12px; color: var(--text-secondary); padding: 8px 0; }
.sess-item {
  display: block; width: 100%; text-align: left; border: none; background: transparent;
  padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 4px;
}
.sess-item:hover { background: #f1f5f9; }
.sess-item.active { background: #eef2ff; }
.sess-title { font-size: 13px; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sess-meta { font-size: 11px; color: var(--text-secondary); }
.main-pane { flex: 1; min-width: 0; }
.turn-controls { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.hero-card, .plan-card, .clarify-card, .run-card, .result-card, .adv-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: var(--radius-md, 10px);
  padding: 16px;
  margin-bottom: 12px;
}
.hero-card h3 { margin: 0 0 12px; }
.prep { margin: 12px 0; padding: 10px 12px; background: #f8fafc; border-radius: 8px; }
.prep-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.main-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.sess-heading { margin: 0 0 6px; font-size: 18px; }
.head-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.thread {
  display: flex;
  flex-direction: column;
  height: min(560px, 68vh);
  margin-bottom: 12px;
  overflow: hidden;
  background: #f8fafc;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 12px;
}
.thread-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: #fff;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
}
.thread-head .plan-title { margin: 0; }
.thread-log { flex: 1; min-height: 0; overflow-y: auto; padding: 14px; }
.thread-empty { padding: 28px 8px; text-align: center; font-size: 13px; color: var(--text-secondary); }
.msg {
  max-width: min(760px, 92%);
  margin: 0 0 12px;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fff;
  font-size: 13px;
}
.msg.user { margin-left: auto; background: #eef2ff; border-color: #c7d2fe; }
.msg.system { max-width: 100%; background: transparent; border-style: dashed; }
.msg-meta { display: flex; gap: 8px; align-items: baseline; margin-bottom: 4px; font-size: 12px; color: var(--text-secondary); }
.msg-meta b { color: var(--text-primary, #0f172a); }
.msg-meta { flex-wrap: wrap; }
.agent-origin { display: inline-flex; padding: 1px 7px; border: 1px solid var(--el-color-primary-light-7); border-radius: 5px; background: var(--el-color-primary-light-9); color: var(--el-color-primary); font-size: 11px; line-height: 1.6; }
.agent-origin.sub-agent { border-color: var(--el-color-success-light-7); background: var(--el-color-success-light-9); color: var(--el-color-success); }
.msg-body { font-size: 14px; min-width: 0; }
.composer { margin: 0; padding: 10px 12px 12px; background: #fff; border-top: 1px solid var(--border-color, #e2e8f0); }
.composer-bar { display: flex; gap: 12px; align-items: center; justify-content: space-between; margin-top: 8px; }
.plan-title { font-weight: 600; margin-bottom: 8px; }
.plan-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }
.plan-head .plan-title { margin: 0; }
.plan-edit { max-width: 680px; }
.event-title { font-weight: 600; font-size: 13px; }
.event-detail { margin: 4px 0 0; font-size: 13px; line-height: 1.55; color: var(--text-secondary); }
:global(.main) { overflow-anchor: none; }
.plan-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.clarify-lead { margin: 0 0 12px; font-size: 13px; line-height: 1.5; color: var(--text-secondary); }
.clarify-block { margin-bottom: 14px; }
.clarify-label { font-size: 14px; font-weight: 600; line-height: 1.4; margin-bottom: 4px; color: var(--text-primary, #0f172a); }
.clarify-q { font-size: 13px; line-height: 1.5; color: var(--text-secondary); margin: 0 0 8px; }
.clarify-block :deep(.el-input-number),
.clarify-block :deep(.el-select),
.clarify-block :deep(.resource-picker) { width: 100%; max-width: 520px; }
.gap-alert { margin-bottom: 12px; }
.budget-box {
  margin-bottom: 14px;
  padding: 12px;
  border-radius: 8px;
  background: #fff7ed;
  border: 1px solid #fdba74;
}
.budget-box :deep(.el-input-number) { width: 220px; }
.action-dock {
  position: sticky;
  bottom: 8px;
  z-index: 4;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 12px 0;
  padding: 12px;
  background: #fff;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}
.dock-hint { flex: 1 1 220px; font-size: 13px; line-height: 1.5; color: var(--text-secondary); }
.empty-note { margin: 0 0 8px; font-size: 13px; line-height: 1.5; color: var(--text-secondary); }
.timeline { max-height: 420px; overflow: auto; margin-top: 8px; padding-right: 8px; }
.payload { font-size: 11px; white-space: pre-wrap; word-break: break-all; max-height: 240px; overflow: auto; }
.cap-card { margin: 12px 0; padding: 12px; background: #f8fafc; border-radius: 8px; }
.cap-card .plan-title { margin-top: 12px; }
.cap-card .plan-title:first-child { margin-top: 0; }
.agent-duty { margin: 4px 0; font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.cap-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.cand-form { margin-bottom: 8px; }
.cand-tools { display: flex; gap: 8px; align-items: center; }
.hint { font-size: 12px; color: var(--text-secondary); }
.warn, .warn-inline { color: var(--el-color-warning); font-size: 12px; }
.link { margin-left: 6px; font-size: 12px; }

/* A focused operations workspace: conversation first, evidence one tab away. */
.agents-wb { --rail-w: 250px; --assistant-accent: #087f85; }
.page-header { display: flex; justify-content: space-between; gap: 24px; align-items: center; padding-bottom: 18px; border-bottom: 1px solid #e1e9eb; margin-bottom: 20px; }
.page-title { font-size: 24px; letter-spacing: .5px; margin-bottom: 6px; color: #19313c; }
.page-desc { max-width: 760px; line-height: 1.7; color: #657a83; font-size: 13px; }
.session-rail { background: #f8fafb; border-color: #e0e8eb; padding: 14px 10px; }
.rail-head { padding: 0 6px; color: #34505b; font-size: 13px; }
.session-search { margin-bottom: 12px; }
.new-btn { height: 38px; margin-bottom: 12px; }
.sess-item { padding: 12px 10px; margin-bottom: 5px; border: 1px solid transparent; }
.sess-item.active { background: #eaf6f4; border-color: #b8dbd5; box-shadow: inset 3px 0 #087f85; }
.sess-title { font-weight: 500; line-height: 1.65; }
.sess-meta { display: flex; align-items: center; gap: 6px; margin-top: 7px; font-size: 11px; }
.state-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.green { color: #24835e; } .blue { color: #177da6; } .amber { color: #ac6a13; } .red { color: #be4754; } .gray { color: #7d8990; }
.hero-card { max-width: 960px; margin: 0 auto; padding: 28px; }
.hero-kicker { color: #087f85; font-size: 12px; font-weight: 600; margin-bottom: 10px; letter-spacing: 2px; }
.hero-card h3 { font-size: 25px; color: #19313c; }
.hero-card > .hint { margin-bottom: 20px; }
.main-head { padding: 6px 2px 14px; border-bottom: 1px solid #e1e9eb; }
.sess-heading { font-size: 18px; line-height: 1.6; max-width: 760px; }
.head-actions { display: flex; align-items: flex-start; flex-wrap: wrap; gap: 6px; }
.head-actions .el-button + .el-button { margin-left: 0; }
.workflow-steps { display: flex; gap: 6px; margin: 14px 0; overflow-x: auto; }
.workflow-steps span { flex: 1; white-space: nowrap; font-size: 12px; color: #87989f; background: #f3f6f7; padding: 9px 14px; border-bottom: 2px solid transparent; }
.workflow-steps .current { color: #087f85; border-bottom-color: #087f85; background: #edf7f5; }
.workspace-tabs :deep(.el-tabs__header) { margin-bottom: 18px; }
.workspace-tabs :deep(.el-tabs__item) { font-weight: 600; font-size: 14px; }
.thread { height: clamp(720px, 88vh, 1100px); border-color: #dce6e9; border-radius: 10px; background: #fafcfc; }
.thread-head { padding: 12px 20px; }
.thread-log { padding: 22px; scroll-behavior: smooth; }
.msg { max-width: min(900px, 96%); padding: 14px 18px; border-radius: 10px; margin-bottom: 20px; }
.msg.main, .msg.assistant, .msg.monitor, .msg.diagnose { border-color: #e4ecee; background: white; }
.msg.user { background: #eaf5f4; border-color: #cbe3de; max-width: 84%; }
.msg.system { font-size: 12px; padding: 9px 12px; color: #657a83; border: 0; background: #eef3f5; }
.msg-meta { margin-bottom: 10px; font-size: 11px; }
.msg-meta b { font-size: 12px; }
.composer { padding: 14px 18px; }
.composer :deep(.el-textarea__inner) { padding: 12px 14px; line-height: 1.7; border-radius: 8px; }
.continue-analysis { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.continue-analysis span { font-size: 11px; line-height: 1.5; color: #7b8f97; }
.continue-analysis :deep(.el-button) { padding-left: 0; flex-shrink: 0; }
.typing-dots { display: inline-flex; gap: 5px; padding: 8px 0; }
.typing-dots i { width: 7px; height: 7px; background: #5c9997; border-radius: 50%; animation: assistant-dot 1.25s infinite ease-in-out; }
.typing-dots i:nth-child(2) { animation-delay: .18s; } .typing-dots i:nth-child(3) { animation-delay: .36s; }
@keyframes assistant-dot { 0%,60%,100% { opacity:.35; transform:translateY(0); } 30% { opacity:1; transform:translateY(-4px); } }
@media(prefers-reduced-motion: reduce) { .typing-dots i { animation: none; } .thread-log { scroll-behavior: auto; } }
.delivery-note { display: block; font-size: 11px; color: #718892; margin-top: 8px; }
.delivery-note.failed { color: #be4754; }
.round-help { font-size: 11px; color: #087f85; cursor: help; margin: 0 8px; }
.plan-card { margin-top: 16px; }
.plan-list { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px 20px; list-style: none; padding-left: 0; }
.action-dock { box-shadow: 0 4px 16px rgba(25,49,60,.05); border-color: #dce6e9; }
@media(max-width: 700px) { .page-header { align-items: flex-start; gap: 10px; } .hero-card { padding: 18px; } .thread-log { padding: 12px; } .msg { padding: 12px; max-width: 100%; } .msg.user { max-width: 94%; } .workflow-steps span { padding: 8px; } .plan-list { grid-template-columns: 1fr; } .continue-analysis { align-items: flex-start; flex-direction: column; gap: 0; } }
@media (max-width: 1024px) {
  .wb-layout { flex-direction: column; }
  .main-pane { width: 100%; }
  .session-rail { position: static; width: 100%; max-height: 280px; }
  .thread { height: max(720px, 88vh); }
  .composer-bar { flex-direction: column; align-items: stretch; }
}
.cap-card { border: 1px solid #b8d5d7; padding: 8px 18px; margin: 22px 0; }
.cap-card :deep(.el-collapse-item__header), .cap-card :deep(.el-collapse-item__wrap) { background: transparent; }
.cap-card :deep(.el-collapse-item__header) { font-weight: 600; }
.cap-card :deep(.el-collapse-item__content) { padding: 12px 0 20px; }
.cap-card :deep(.el-checkbox-group) { display: flex; flex-wrap: wrap; gap: 10px 12px; margin: 16px 0; }
.cap-card :deep(.el-checkbox) { margin: 0; padding: 8px 12px; height: auto; border: 1px solid #cddde0; border-radius: 7px; background: var(--bg-card); }
.cap-card :deep(.el-checkbox.is-checked) { border-color: #6ea9a5; background: #edf7f5; }
.cap-card .plan-title:not(:first-child) { margin-top: 24px; }
.agent-duty { padding: 9px 12px; margin: 6px 0; border-left: 2px solid #b8d5d7; line-height: 1.8; }
.dark .agents-wb { --assistant-accent: #71d0c6; color: var(--text-primary); }
.dark .agents-wb .page-title, .dark .agents-wb .hero-card h3, .dark .agents-wb .rail-head { color: #e2edf4; }
.dark .agents-wb .page-desc, .dark .agents-wb .continue-analysis span { color: #a5b8ca; }
.dark .agents-wb .session-rail, .dark .agents-wb .thread { background: #162235; border-color: #35485c; }
.dark .agents-wb .thread-head, .dark .agents-wb .composer, .dark .agents-wb .msg.main, .dark .agents-wb .msg.assistant, .dark .agents-wb .msg.monitor, .dark .agents-wb .msg.diagnose { background: #1e293b; border-color: #35485c; }
.dark .agents-wb .msg.user, .dark .agents-wb .sess-item.active { background: #173b40; border-color: #3f7777; }
.dark .agents-wb .sess-item:hover { background: #26394c; }
.dark .agents-wb .msg.system, .dark .agents-wb .prep, .dark .agents-wb .cap-card { background: #17283a; color: #afc1d0; border-color: #3c6270; }
.dark .agents-wb .workflow-steps span { background: #1b2b40; color: #a1b2c7; }
.dark .agents-wb .workflow-steps .current { background: #173b40; color: #83d8cd; }
.dark .agents-wb .page-header, .dark .agents-wb .main-head, .dark .agents-wb .action-dock { border-color: #35485c; }
.dark .agents-wb .green { color: #78d8aa; } .dark .agents-wb .blue { color: #82c9f4; } .dark .agents-wb .amber { color: #f2c06f; } .dark .agents-wb .red { color: #f997a4; } .dark .agents-wb .gray { color: #a6b7c7; }
.dark .agents-wb .cap-card :deep(.el-checkbox) { border-color: #466071; }
.dark .agents-wb .cap-card :deep(.el-checkbox.is-checked) { background: #173b40; border-color: #6fa9a6; }
.dark .agents-wb .round-help, .dark .agents-wb .hero-kicker { color: #83d8cd; }
</style>
