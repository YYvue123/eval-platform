<template>
  <div class="agents-wb">
    <div class="page-header">
      <div>
        <h2 class="page-title">评测助手</h2>
        <p class="page-desc">主 Agent 是唯一入口。监控分析与异常诊断跟随每个任务；方案分析、报告审校、参数推荐以及自定义子 Agent 由主 Agent 按需调用。诊断只给建议，恢复和补测仍要确认后才执行。</p>
      </div>
    </div>

    <el-card class="profile-card" shadow="never">
      <el-collapse v-model="profilePanel">
        <el-collapse-item title="主 Agent · coordinator" name="profile">
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
            <el-form-item label="temperature">
              <el-input-number v-model="profileForm.temperature" :min="0" :max="2" :step="0.1" :disabled="!canEditProfile" />
            </el-form-item>
            <el-form-item label="max_tokens">
              <el-input-number v-model="profileForm.max_tokens" :min="0" :max="8192" :step="64" :disabled="!canEditProfile" />
              <span class="hint">0 表示不额外截断。大于 0 时，模型请求和最终回复都受这个上限约束。</span>
            </el-form-item>
            <el-form-item label="最大迭代">
              <el-input-number v-model="profileForm.max_iterations" :min="1" :max="20" :disabled="!canEditProfile" />
            </el-form-item>
            <el-form-item label="子 Agent 超时">
              <el-input-number v-model="profileForm.timeout_seconds" :min="5" :max="600" :disabled="!canEditProfile" />
              <span class="hint">秒。超时后终止该次调用，并把失败返回主 Agent。</span>
            </el-form-item>
            <el-form-item label="流式输出">
              <el-switch v-model="profileForm.supports_stream" :disabled="!canEditProfile" />
              <span class="hint">打开后，消息接口返回运行流地址。页面里的继续对话仍等本轮结束。</span>
            </el-form-item>
            <el-form-item label="人工介入">
              <el-switch v-model="profileForm.human_in_the_loop" :disabled="!canEditProfile" />
            </el-form-item>
            <el-form-item label="可调用工具">
              <el-checkbox-group v-model="profileForm.available_tools" :disabled="!canEditProfile">
                <el-checkbox v-for="tool in mainToolOptions" :key="tool.name" :label="tool.name">{{ tool.label }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="评测标尺">
              <el-input
                v-model="profileForm.evaluation_spec_text"
                type="textarea"
                :rows="3"
                placeholder="主 Agent 一般留空。评测 Agent 才需要 JSON，例如 metric_names"
                :disabled="!canEditProfile"
              />
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

    <div class="wb-layout">
      <aside class="session-rail" :class="{ collapsed: railCollapsed }">
        <div class="rail-head">
          <span>会话</span>
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
          <div v-if="sessionsLoadError" class="rail-empty">{{ sessionsLoadError }}</div>
          <div v-else-if="!sessions.length" class="rail-empty">暂无会话</div>
          <button
            v-for="s in sessions"
            :key="s.id"
            type="button"
            class="sess-item"
            :class="{ active: currentId === s.id }"
            @click="selectSession(s.id)"
          >
            <div class="sess-title">#{{ s.id }} {{ s.title || '未命名' }}</div>
            <div class="sess-meta">{{ s.status }}</div>
          </button>
        </div>
      </aside>

      <main class="main-pane">
        <!-- 无会话：起步 -->
        <section v-if="!currentId" class="hero-card">
          <h3>描述你想完成的评测</h3>
          <el-input
            v-model="goalText"
            type="textarea"
            :rows="4"
            placeholder="例如：对金融场景做智能对话正式评测，使用已发布数据集与已配置连接的模型"
          />
          <div class="prep">
            <div class="prep-row">
              <span>规划模型（Runtime）</span>
              <StatusBadge v-if="plannerModels.length" phase="approved" text="已配置" />
              <StatusBadge v-else phase="failed" text="真实模型未配置" />
              <router-link v-if="userStore.hasPermission('model:create')" class="link" to="/models">去配置模型</router-link>
            </div>
            <div class="prep-row hint">配置完成前不可启动 Runtime；正式评测还需数据集与被测模型。</div>
          </div>
          <el-collapse v-model="budgetPanel">
            <el-collapse-item title="高级：预算与规划模型" name="adv">
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
          <section class="cap-card">
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

          </section>
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
                <StatusBadge :phase="productPhase" />
                <el-tag v-if="session.plan?.trial_run" size="small" type="info">试跑</el-tag>
                <el-tag v-else-if="session.plan?.ready" size="small">正式</el-tag>
                <span v-if="session.plan?.token_budget != null" class="hint">计划预算 {{ session.plan.token_budget }}</span>
                <span v-if="pollError" class="warn-inline">{{ pollError }}</span>
              </div>
            </div>
            <div class="head-actions">
              <el-button size="small" @click="drawerOpen = true">计划 / 证据</el-button>
            </div>
          </div>

          <div v-if="sessionLoading && !session.id" class="hint">加载会话…</div>

          <section class="thread">
            <div class="thread-head">
              <div>
                <div class="plan-title">对话</div>
                <span class="hint">{{ (session.messages || []).length }} 条 · 只在这块区域里滚动</span>
              </div>
              <el-button link size="small" native-type="button" @click="scrollThread(true)">回到最新</el-button>
            </div>
            <div ref="threadLog" class="thread-log" @scroll="onThreadScroll">
              <div v-if="!(session.messages || []).length" class="thread-empty">还没有对话。生成计划后，补充说明会出现在这里。</div>
              <article v-for="m in session.messages || []" :key="m.id" class="msg" :class="m.role">
                <div class="msg-meta">
                  <b>{{ roleLabel(m.role) }}</b>
                  <span v-if="m.created_at">{{ msgTime(m.created_at) }}</span>
                </div>
                <div class="msg-body" v-html="renderMarkdown(m.content)"></div>
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
                <span class="hint">发送后主 Agent 会检索真实资源并改计划。规划模型只负责编排。</span>
                <el-button
                  v-if="userStore.hasPermission('agent:invoke')"
                  type="primary"
                  native-type="button"
                  :loading="runLoading"
                  :disabled="!followUp.trim() || !plannerModelId"
                  @click="sendFollowUp"
                >发送</el-button>
              </div>
            </div>
          </section>

          <!-- 计划摘要卡 -->
          <el-card v-if="session.plan" shadow="never" class="plan-card">
            <div class="plan-head">
              <div class="plan-title">计划摘要</div>
              <el-button size="small" native-type="button" @click="togglePlanEdit">{{ planEditing ? '收起' : '手动修改' }}</el-button>
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
              <el-form-item label="试跑">
                <el-switch v-model="clarifyForm.trial_run" />
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
                这次运行已经用了 <strong>{{ run?.tokens_used || 0 }}</strong> token，限额是
                <strong>{{ run?.token_budget || '未限额' }}</strong>，所以停在预算不足。
                把下面的新预算调大，再点「用新预算重新运行」。执行记录会换成一次新运行；原来这次不会原地继续。
              </p>
              <div class="clarify-label">新的运行预算</div>
              <el-input-number v-model="clarifyForm.token_budget" :min="0" controls-position="right" />
            </div>
            <p v-else class="clarify-lead">每一项单独占一行。提交后计划摘要里的数字会变，旧审批作废，需要重新审批。</p>
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
              <div class="clarify-label">试用模式</div>
              <p class="clarify-q">开启后按小规模真实样本执行，用量计入同一预算。正式评测需要正数 Token 预算，并满足数据和模型门禁。</p>
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
            <el-button @click="toggleAdvanced">{{ showAdvanced ? '收起高级' : '高级' }}</el-button>
            <span v-if="primaryHint" class="dock-hint">{{ primaryHint }}</span>
          </div>

          <el-card v-if="showAdvanced" shadow="never" class="adv-card">
            <el-tabs>
              <el-tab-pane label="Runtime">
                <el-form label-width="100px" size="small">
                  <el-form-item label="规划模型">
                    <el-select v-model="plannerModelId" clearable filterable placeholder="必选" style="width: 100%">
                      <el-option v-for="m in plannerModels" :key="m.id" :label="m.name" :value="m.id" />
                    </el-select>
                    <div v-if="modelsLoadError" class="hint">{{ modelsLoadError }}</div>
                  </el-form-item>
                </el-form>
                <el-button
                  v-if="userStore.hasPermission('agent:invoke')"
                  :loading="runLoading"
                  :disabled="!plannerModelId"
                  @click="startRuntime"
                >启动 Runtime 工具循环</el-button>
                <el-button
                  v-if="run && userStore.hasPermission('agent:invoke') && !['success','cancelled','paused_budget'].includes(run.status)"
                  :loading="cancelLoading"
                  @click="cancelRuntime"
                >{{ cancelLoading ? '取消中…' : '取消 run' }}</el-button>
                <el-button
                  v-if="run && userStore.hasPermission('agent:invoke') && ['waiting','failed','queued'].includes(run.status)"
                  type="primary"
                  :loading="resumeLoading"
                  @click="resumeRuntime"
                >从 checkpoint 恢复</el-button>
              </el-tab-pane>
              <el-tab-pane label="知识候选">
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
              </el-tab-pane>
              <el-tab-pane label="子任务 / 建议">
                <p class="empty-note">任务跑起来之后，主 Agent 会在需要时调用监控或诊断。这里只显示已经返回的子任务和建议，没有调用时保持为空。</p>
                <el-table v-if="delegations.length" :data="delegations" size="small">
                  <el-table-column prop="id" label="子任务" width="70" />
                  <el-table-column prop="role" label="角色" width="100" />
                  <el-table-column prop="status" label="状态" width="90" />
                </el-table>
                <p v-if="!delegations.length && !(session.suggestions || []).length" class="empty-note">当前没有子任务，也没有待采纳建议。</p>
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
              </el-tab-pane>
            </el-tabs>
          </el-card>

          <!-- 执行时间线 / 结果 -->
          <el-card v-if="run" shadow="never" class="run-card">
            <div class="plan-head">
              <div class="plan-title">工具循环记录</div>
              <StatusBadge :phase="runPhase" :text="runStatusText" />
            </div>
            <p class="hint">
              第 {{ run.rounds_used || 0 }} / {{ run.max_rounds }} 轮
              · 已用 {{ run.tokens_used || 0 }} token
              · 限额 {{ run.token_budget || '未限额' }}
              <span v-if="run.tokens_usage_unknown"> · 用量未回报</span>
              <span v-if="eventsUpdatedAt"> · {{ eventsUpdatedAt }} 更新</span>
            </p>
            <p v-if="run.error_message" class="warn">{{ run.error_message }}</p>
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

          <el-card v-if="session.task_id && productPhase === 'completed'" shadow="never" class="result-card">
            <div class="plan-title">结果</div>
            <p>已关联任务 #{{ session.task_id }}（{{ session.plan?.trial_run ? '试跑' : '正式' }}）</p>
            <el-button type="primary" link @click="$router.push(`/tasks/${session.task_id}`)">查看任务 / 报告</el-button>
            <el-button v-if="userStore.hasPermission('agent:invoke')" link @click="persistRecipe">沉淀为可复用经验</el-button>
            <el-button link @click="startNew">基于此目标新建</el-button>
          </el-card>
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
        <el-form-item label="流式输出"><el-switch v-model="customAgent.supports_stream" /></el-form-item>
        <el-form-item label="人工介入"><el-switch v-model="customAgent.human_in_the_loop" /></el-form-item>
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
          <el-input v-model="customAgent.evaluation_spec_text" type="textarea" :rows="2" placeholder="评测类子 Agent 填写 JSON" />
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
          <el-select v-model="customSkill.execution_type" style="width: 100%">
            <el-option label="提示词模板" value="prompt_template" />
            <el-option label="工作流" value="workflow" />
            <el-option label="转交子 Agent" value="agent" />
          </el-select>
        </el-form-item>
        <el-form-item label="入口"><el-input v-model="customSkill.entry_point" type="textarea" :rows="3" placeholder="提示词，或 knowledge.search" /></el-form-item>
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

const userStore = useUserStore()
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
  { name: 'search_knowledge', label: '检索经验知识' },
  { name: 'infer_dims', label: '推断场景' },
  { name: 'search_eval_resources', label: '检索评测资源' },
  { name: 'propose_resources', label: '写入计划' },
  { name: 'delegate_agent', label: '调用子 Agent' },
  { name: 'invoke_skill', label: '调用 Skill' },
  { name: 'call_mcp', label: '调用 MCP' },
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
const showAdvanced = ref(false)
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
const showClarify = computed(() => ['needs_input', 'awaiting_approval', 'planning', 'budget_paused'].includes(productPhase.value))
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

const judgeLabel = computed(() => {
  const id = session.value?.plan?.judge_resource_id
  if (!id) return '—'
  return judgeOptions.value.find((item) => item.resource_id === id)?.name || id
})

const runStatusText = computed(() => ({
  queued: '排队',
  running: '进行中',
  waiting: '等待',
  success: '完成',
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
  const map = {
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
    const s = JSON.stringify(p, null, 2)
    return s.length > 2000 ? `${s.slice(0, 2000)}\n…` : s
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
  const r = run.value
  if (!currentId.value || !s?.id) return 'idle'
  if (r?.status === 'paused_budget') return 'budget_paused'
  if (r?.status === 'cancelled') return 'cancelled'
  if (r?.status === 'failed') return 'failed'
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
    if (s.plan?.ready && (s.status === 'waiting_confirm' || s.status === 'approved')) return 'awaiting_approval'
    if (!s.plan?.ready || (s.plan?.clarifications || []).length) return 'needs_input'
    return 'completed'
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
    if (run.value && ['waiting', 'failed', 'queued'].includes(run.value.status)) return { key: 'resume', label: '安全恢复' }
    if (session.value?.task_id) return { key: 'view_task', label: '查看失败任务' }
    return { key: 'clarify', label: '修改计划' }
  }
  if (p === 'cancelled') return { key: 'restart', label: '基于此目标新建' }
  if (p === 'budget_paused') return { key: 'raise_budget', label: '用新预算重新运行' }
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
  if (k === 'resume') return resumeLoading.value
  return false
})

const primaryDisabled = computed(() => {
  if (primaryAction.value?.disabled) return true
  const k = primaryAction.value?.key
  if (k === 'approve' && !userStore.hasPermission('agent:confirm')) return true
  if (k === 'confirm' && (!userStore.hasPermission('agent:confirm') || !activeApproval.value)) return true
  if ((k === 'clarify' || k === 'raise_budget') && !userStore.hasPermission('agent:invoke')) return true
  return false
})

const primaryHint = computed(() => {
  const p = productPhase.value
  if (p === 'approved' && !activeApproval.value) return '审批已失效，请重新签发后再执行。'
  if (p === 'budget_paused') return '新预算必须大于这次已用 token。确认后会重新启动一次运行，执行记录换成新的 run。'
  if (p === 'needs_input' || p === 'planning') return '补全缺项后点「补充并更新计划」。计划就绪后，主按钮会变成「审批计划」。'
  if (p === 'awaiting_approval') return '核对数据集、模型和预算后审批。若要改配置，点「保存计划修改」，旧审批会失效。'
  if (p === 'cancelled') return '本次运行已取消，可以基于同一目标新建会话。'
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

function toggleAdvanced() {
  showAdvanced.value = !showAdvanced.value
  if (showAdvanced.value) {
    loadCandidates().catch(() => {})
    if (currentId.value && session.value?.task_id) loadDelegations().catch(() => {})
  }
}

async function runPrimary() {
  const k = primaryAction.value?.key
  if (k === 'clarify') return clarify()
  if (k === 'approve') return approve()
  if (k === 'confirm') return confirm(true)
  if (k === 'view_task' || k === 'report') {
    if (session.value.task_id) router.push(`/tasks/${session.value.task_id}`)
    return
  }
  if (k === 'resume') return resumeRuntime()
  if (k === 'restart') return startNew()
  if (k === 'raise_budget') return raiseBudgetAndRerun()
}

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function resetRunContext() {
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
  session.value = {}
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
    if (data.task_id) await loadDelegations(sid, gen)
    const runId = data.active_run_id || data.last_run_id
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
  const res = await agentsApi.delegations(sid)
  if (gen !== sessionGen || currentId.value !== sid) return
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
      execution_type: row.execution_type || 'prompt_template',
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
    const payload = { ...customSkill.value }
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
    ElMessage.success(created.plan?.ready ? '计划已就绪，可审批' : '需要补充信息')
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
  resetRunContext()
  const data = await agentsApi.getRun(rid)
  if (gen !== sessionGen || currentId.value !== sid) return
  run.value = data
  const res = await agentsApi.runEvents(rid, { after_seq: 0 })
  if (gen !== sessionGen || currentId.value !== sid) return
  events.value = []
  seenEventSeq = new Set()
  eventCursor = 0
  mergeEvents(res.items || [], rid)
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
    pollError.value = ''
  } catch (e) {
    if (gen === sessionGen) pollError.value = e?.response?.data?.detail || e?.message || '刷新失败'
  } finally {
    pollInFlight.value = false
  }
}

function schedulePoll() {
  stopPoll()
  const tick = async () => {
    if (!run.value?.id) return
    if (['success', 'failed', 'cancelled', 'paused_budget'].includes(run.value.status)) {
      stopPoll()
      return
    }
    await refreshRun()
    if (!run.value?.id) return
    if (['success', 'failed', 'cancelled', 'paused_budget'].includes(run.value.status)) {
      stopPoll()
      return
    }
    pollTimer = setTimeout(tick, 2000)
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

async function raiseBudgetAndRerun() {
  const used = Number(run.value?.tokens_used || 0)
  const oldCap = Number(run.value?.token_budget || 0)
  const next = Number(clarifyForm.value.token_budget || 0)
  const floor = Math.max(used, oldCap)
  if (next <= floor) {
    ElMessage.warning(`新预算需要大于 ${floor}。这次已用 ${used}，原限额 ${oldCap || '未限额'}。`)
    return
  }
  if (!plannerModelId.value && run.value?.planner_model_id) {
    plannerModelId.value = run.value.planner_model_id
  }
  if (!plannerModelId.value) {
    showAdvanced.value = true
    ElMessage.warning('请在按钮下方的高级面板里选择规划模型')
    return
  }
  clarifying.value = true
  const prevPlan = Number(session.value?.plan?.token_budget || 0)
  try {
    const payload = {
      objective: goalText.value || session.value.requirement,
      trial_run: clarifyForm.value.trial_run,
      token_budget: next,
    }
    if (clarifyForm.value.dataset_id) payload.dataset_id = clarifyForm.value.dataset_id
    if (clarifyForm.value.model_id) payload.model_id = clarifyForm.value.model_id
    await agentsApi.clarify(currentId.value, payload)
    tokenBudget.value = next
    await launchRuntime({ quiet: true, budget: next })
    ElMessage.success(`运行限额已从 ${oldCap || '未限额'} 提高到 ${next}，计划预算从 ${prevPlan} 改为 ${next}。下方执行记录已换成新的运行。`)
  } catch (e) {
    await loadSession().catch(() => {})
    ElMessage.error(e?.response?.data?.detail || e?.message || '调整预算失败')
  } finally {
    clarifying.value = false
  }
}

function startRuntime() {
  return launchRuntime({}).catch(() => {})
}

async function sendFollowUp() {
  const text = followUp.value.trim()
  if (!text || runLoading.value) return
  try {
    await launchRuntime({ message: text })
    followUp.value = ''
  } catch {
    /* launchRuntime 已提示 */
  }
}

function inlineMarkdown(text) {
  return text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
}

function renderMarkdown(raw) {
  const escaped = String(raw || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  const blocks = []
  const withCode = escaped.replace(/```([\s\S]*?)```/g, (_, code) => {
    const token = `@@CODE${blocks.length}@@`
    blocks.push(`<pre><code>${code.replace(/^\n|\n$/g, '')}</code></pre>`)
    return token
  })
  const html = withCode
    .split(/\n{2,}/)
    .map((para) => {
      const lines = para.split('\n')
      const tableLines = lines.map((line) => line.trim()).filter(Boolean)
      const isTable = tableLines.length >= 2 && tableLines.every((line) => line.startsWith('|') && line.endsWith('|'))
      if (isTable) {
        const rows = tableLines
          .map((line) => line.slice(1, -1).split('|').map((cell) => inlineMarkdown(cell.trim())))
          .filter((row) => !row.every((cell) => /^:?-{3,}:?$/.test(cell)))
        if (rows.length) {
          const head = rows[0].map((cell) => `<th>${cell}</th>`).join('')
          const body = rows.slice(1).map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join('')}</tr>`).join('')
          return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`
        }
      }
      let line = inlineMarkdown(para)
      line = line.replace(/^#{1,3} (.+)$/gm, '<strong>$1</strong>')
      line = line.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
      line = line.replace(/^(?:[-*] |\d+\. )(.+)$/gm, '<li>$1</li>')
      if (line.includes('<li>')) line = `<ul>${line}</ul>`
      return `<p>${line.replace(/\n/g, '<br>')}</p>`
    })
    .join('')
  return html.replace(/@@CODE(\d+)@@/g, (_, index) => blocks[Number(index)] || '')
}

async function launchRuntime({ quiet = false, budget = null, message = '' } = {}) {
  if (!currentId.value || !plannerModelId.value) {
    ElMessage.warning('请选择已配置 api_url 的规划模型')
    return
  }
  runLoading.value = true
  const sid = currentId.value
  const gen = sessionGen
  const nextBudget = budget == null ? Number(clarifyForm.value.token_budget || tokenBudget.value || 0) : Number(budget)
  const text = String(message || goalText.value || session.value.requirement || '').trim()
  try {
    const data = await agentsApi.startRun(sid, {
      message: text,
      provider: 'live',
      planner_model_id: plannerModelId.value,
      token_budget: nextBudget,
      sync: true,
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

async function cancelRuntime() {
  if (!run.value?.id || cancelLoading.value) return
  cancelLoading.value = true
  try {
    run.value = await agentsApi.cancelRun(run.value.id)
    await refreshRun()
    ElMessage.success(run.value.status === 'cancelled' ? '已取消' : '已请求取消')
    if (!['cancelled', 'success', 'failed'].includes(run.value.status)) schedulePoll()
  } finally {
    cancelLoading.value = false
  }
}

async function resumeRuntime() {
  if (!run.value?.id || resumeLoading.value) return
  resumeLoading.value = true
  try {
    run.value = await agentsApi.resumeRun(run.value.id)
    await refreshRun()
    await loadSession()
    ElMessage.success(`恢复后 ${run.value.status}`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '恢复失败')
  } finally {
    resumeLoading.value = false
  }
}

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
      human_in_the_loop: profileForm.value.human_in_the_loop,
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
  document.removeEventListener('click', rememberPageClick, true)
  sessionGen += 1
  stopPoll()
})
</script>

<style scoped>
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
.msg-body { line-height: 1.6; word-break: break-word; }
.msg-body :deep(p) { margin: 0 0 6px; }
.msg-body :deep(p:last-child) { margin-bottom: 0; }
.msg-body :deep(ul) { margin: 4px 0; padding-left: 18px; }
.msg-body :deep(code) { padding: 0 4px; border-radius: 4px; background: rgba(15, 23, 42, 0.06); }
.msg-body :deep(table) { width: 100%; border-collapse: collapse; margin: 6px 0; }
.msg-body :deep(th), .msg-body :deep(td) { border: 1px solid #e2e8f0; padding: 4px 6px; text-align: left; vertical-align: top; }
.msg-body :deep(blockquote) { margin: 6px 0; padding-left: 8px; border-left: 3px solid #cbd5e1; color: var(--text-secondary); }
.msg-body :deep(pre) { margin: 6px 0; padding: 8px; overflow: auto; border-radius: 6px; background: #0f172a; color: #e2e8f0; }
.msg-body :deep(pre code) { padding: 0; background: transparent; color: inherit; }
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
@media (max-width: 1024px) {
  .wb-layout { flex-direction: column; }
  .session-rail { position: static; width: 100%; max-height: 280px; }
  .thread { height: min(480px, 70vh); }
  .composer-bar { flex-direction: column; align-items: stretch; }
}
</style>
