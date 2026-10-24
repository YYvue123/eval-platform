<template>
  <el-drawer v-model="visible" title="榜单管理" size="min(720px, 96vw)" destroy-on-close>
    <p class="context">{{ datasetLabel(data.cohorts?.find(c=>c.id===data.cohort_id)?.dataset_name) || '当前比较组' }}</p>
    <el-tabs v-model="active">
      <el-tab-pane label="发布与期数" name="publications">
        <div v-if="user.hasPermission('leaderboard:publish')" class="form-box">
          <h3>发布当前筛选结果</h3><p>冻结当前分数、权重、模型版本和评测范围。后续评测不会改动已发布期数。</p>
          <el-input v-model="title" placeholder="例如：2026年10月 · 第一期" maxlength="120" />
          <el-checkbox v-model="publicAccess">同时生成免登录公开链接（仅公开模型名称与汇总指标）</el-checkbox>
          <el-button type="primary" :loading="saving" :disabled="!data.items?.length || !title.trim()" @click="publish">确认发布</el-button>
        </div>
        <el-empty v-if="!publications.length" description="尚无已发布期数" :image-size="70" />
        <article v-for="p in publications" :key="p.id" class="publication">
          <div><b>{{ p.title }}</b><el-tag :type="p.status==='published'?'success':'info'" size="small">{{ p.status==='published'?'已发布':'已撤回' }}</el-tag></div>
          <small>#{{ p.id }} · {{ date(p.created_at) }} · {{ boardNames[p.board] }}</small>
          <p v-if="p.withdrawal_reason" class="reason">撤回原因：{{ p.withdrawal_reason }}</p>
          <small class="checksum">内容校验 {{ p.checksum?.slice(0,16) }}</small>
          <div class="actions"><el-button v-if="user.hasPermission('leaderboard:view')" link type="primary" @click="$emit('snapshot',p.id);visible=false">查看快照</el-button>
            <a v-if="p.public_path" :href="p.public_path" target="_blank" rel="noopener">公开页面</a>
            <el-button v-if="p.status==='published' && user.hasPermission('leaderboard:withdraw')" link type="danger" @click="withdraw(p)">撤回本期</el-button>
          </div>
        </article>
      </el-tab-pane>
      <el-tab-pane v-if="user.hasPermission('leaderboard:edit')" label="综合权重" name="weights">
        <p class="context">按维度加权，不混合不同评测工具的分数。保存只影响实时榜；已发布快照保留原权重。</p>
        <div v-for="r in weightRows" :key="r.name" class="weight-row"><span>{{ r.name }}</span><el-input-number v-model="r.weight" :min="0" :max="100" :step="1" /><b>{{ weightTotal ? (r.weight/weightTotal*100).toFixed(1) : '0' }}%</b></div>
        <p>合计 {{ weightTotal }}，系统按比例归一。零权重表示该维度不参与综合分。</p>
        <el-button v-if="user.hasPermission('leaderboard:edit')" type="primary" :loading="saving" :disabled="!data.scale || !weightTotal" @click="saveWeights">保存权重并重算</el-button>
      </el-tab-pane>
      <el-tab-pane v-if="user.hasPermission('leaderboard:review')" label="异常复核" name="reviews">
        <div class="form-box"><h3>提交来源任务复核</h3><p>待复核任务暂停入榜，关联发布记录自动撤回；原始成绩不被改写。</p><el-input-number v-model="reportTask" :min="1" placeholder="来源任务 ID" /><el-input v-model="reason" type="textarea" :rows="3" placeholder="说明疑点和需要核查的证据（至少4字）" maxlength="500" /><el-button v-if="user.hasPermission('leaderboard:review')" type="primary" :disabled="!reportTask || reason.trim().length<4" :loading="saving" @click="report">提交复核</el-button></div>
        <el-empty v-if="!reviews.length" description="暂无复核记录" :image-size="70" />
        <article v-for="r in reviews" :key="r.id" class="publication"><div><b>任务 #{{ r.task_id }}</b><el-tag :type="r.status==='pending'?'warning':r.status==='excluded'?'danger':'success'" size="small">{{ {pending:'待复核',excluded:'已排除',cleared:'已恢复'}[r.status] }}</el-tag></div><p>{{ r.reason }}</p><p v-if="r.decision_note">处理意见：{{ r.decision_note }}</p><div class="actions" v-if="r.status==='pending'"><el-button v-if="user.hasPermission('leaderboard:review')" type="success" plain size="small" @click="resolve(r,'cleared')">核查无误，恢复入榜</el-button><el-button v-if="user.hasPermission('leaderboard:review')" type="danger" plain size="small" @click="resolve(r,'excluded')">确认异常，排除结果</el-button></div></article>
      </el-tab-pane>
      <el-tab-pane v-if="user.hasPermission('leaderboard:edit')" label="计价配置" name="costs">
        <p class="context">费用是实测 Token 与耗时乘以配置单价的估算，不是供应商账单。未配置的模型不参与性价比排名。计价单位需由运营统一。</p>
        <article v-for="r in costs" :key="r.model_id" class="publication"><b>{{ r.model_name }}</b><small>{{ r.configured ? '已配置单价' : '尚未配置' }}</small><div class="pricing"><label>每千 Token<el-input-number v-model="r.token_price_per_1k" :min="0" :step="0.001" :precision="6" /></label><label>每秒响应耗时<el-input-number v-model="r.latency_price_per_sec" :min="0" :step="0.001" :precision="6" /></label><label>每 GPU 小时<el-input-number v-model="r.gpu_hour_price" :min="0" :step="0.1" /></label></div><el-button v-if="user.hasPermission('leaderboard:edit')" size="small" :loading="saving" @click="saveCost(r)">保存此模型单价</el-button></article>
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>
<script setup>
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { leaderboardApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { datasetLabel } from '@/utils/evaluationLabels'
const props=defineProps({data:{type:Object,default:()=>({})},context:Object})
const emit=defineEmits(['refresh','snapshot'])
const user=useUserStore(), visible=ref(false), active=ref('publications'), saving=ref(false)
const publications=ref([]), reviews=ref([]), costs=ref([]), weightRows=ref([]), title=ref(''), publicAccess=ref(false), reportTask=ref(null),reason=ref('')
const boardNames={overall:'综合得分榜',ability:'单项能力榜',special:'专项评测榜',value:'性价比榜'}
const weightTotal=computed(()=>weightRows.value.reduce((s,r)=>s+(Number(r.weight)||0),0))
const date=v=>v?new Date(`${v}Z`).toLocaleString('zh-CN'):'—'
const message=e=>e.response?.data?.detail || e.message || '操作失败'
async function reload(){
  publications.value=(await leaderboardApi.publications({cohort_id:props.data.cohort_id})).items
  if(user.hasPermission('leaderboard:review')) reviews.value=(await leaderboardApi.reviews()).items
  if(user.hasPermission('leaderboard:edit')) costs.value=(await leaderboardApi.costs()).items.filter(r=>props.data.items?.some(m=>m.model_id===r.model_id)).map(r=>({...r,token_price_per_1k:r.token_price_per_1k??0,latency_price_per_sec:r.latency_price_per_sec??0,gpu_hour_price:r.gpu_hour_price??0}))
}
async function open(tab='publications',taskId=null){active.value=tab;visible.value=true;reportTask.value=taskId;reason.value='';title.value=`${new Date().getFullYear()}年${new Date().getMonth()+1}月 · ${boardNames[props.context.board]}`;publicAccess.value=false;weightRows.value=(props.data.dimensions||[]).map(name=>({name,weight:props.data.weights?.[name]??1}));try{await reload()}catch(e){ElMessage.error(message(e))}}
async function perform(fn){saving.value=true;try{await fn();await reload();emit('refresh');ElMessage.success('操作已保存')}catch(e){ElMessage.error(message(e))}finally{saving.value=false}}
async function publish(){await perform(()=>leaderboardApi.publishSnapshot({...props.context,title:title.value.trim(),public:publicAccess.value}))}
async function withdraw(p){try{const {value}=await ElMessageBox.prompt('撤回后公开链接立即失效，历史内容保留用于审计。请填写原因。','撤回榜单',{inputValidator:v=>v?.trim().length>=4 || '至少填写4字原因',confirmButtonText:'确认撤回',cancelButtonText:'取消'});await perform(()=>leaderboardApi.withdrawSnapshot(p.id,{reason:value.trim()}))}catch(e){if(e!=='cancel'&&e!=='close')ElMessage.error(message(e))}}
async function saveWeights(){await perform(()=>leaderboardApi.policy({cohort_id:props.data.cohort_id,weights:Object.fromEntries(weightRows.value.map(r=>[r.name,r.weight]))}))}
async function report(){await perform(()=>leaderboardApi.report({task_id:reportTask.value,reason:reason.value.trim()}));reason.value=''}
async function resolve(r,decision){try{const {value}=await ElMessageBox.prompt('请填写核查依据。恢复结果不会自动重新发布已撤回的期数。','完成异常复核',{inputValidator:v=>v?.trim().length>=4 || '至少填写4字依据'});await perform(()=>leaderboardApi.resolveReview(r.id,{decision,note:value.trim()}))}catch(e){if(e!=='cancel'&&e!=='close')ElMessage.error(message(e))}}
async function saveCost(r){await perform(()=>leaderboardApi.putCost(r.model_id,{token_price_per_1k:r.token_price_per_1k,latency_price_per_sec:r.latency_price_per_sec,gpu_hour_price:r.gpu_hour_price}))}
defineExpose({open})
</script>
<style scoped>
.context{font-size:12px;color:var(--text-secondary);line-height:1.9;margin:0 0 20px}.form-box{padding:18px;background:var(--bg-page,#f7f9fd);border-radius:10px;display:flex;flex-direction:column;align-items:flex-start;gap:14px;margin-bottom:22px}.form-box h3,.form-box p{margin:0}.form-box p{font-size:12px;color:var(--text-secondary);line-height:1.8}.form-box :deep(.el-input),.form-box :deep(.el-textarea){width:100%}.publication{border:1px solid var(--border-color);border-radius:10px;padding:18px;margin-bottom:14px}.publication>div:first-child{display:flex;justify-content:space-between;gap:12px}.publication small{display:block;color:var(--text-secondary);margin:8px 0;font-size:11px}.publication p{font-size:13px;line-height:1.8;overflow-wrap:anywhere}.checksum{font-family:monospace}.actions{display:flex;align-items:center;gap:16px;margin-top:12px}.actions a{font-size:12px;color:var(--el-color-primary)}.weight-row{display:grid;grid-template-columns:1fr 160px 70px;align-items:center;gap:18px;margin:16px 0}.weight-row b{font-size:13px;color:var(--el-color-primary)}.pricing{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.pricing label{font-size:12px;display:flex;flex-direction:column;gap:8px;color:var(--text-secondary)}.pricing :deep(.el-input-number){width:160px}
</style>
