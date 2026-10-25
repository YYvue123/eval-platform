<template>
  <el-dialog :model-value="modelValue" :title="sample?'编辑基准题目':'新增基准题目'" width="min(900px,95vw)" :close-on-click-modal="false" @update:model-value="emit('update:modelValue',$event)">
    <el-form label-width="110px" label-position="right">
      <el-row :gutter="20"><el-col :span="14"><el-form-item label="评测指标" required><el-select v-model="form.dimension" style="width:100%" @change="dimensionChanged"><el-option v-for="(label,key) in dimensions" :key="key" :value="key" :label="label"/></el-select></el-form-item></el-col><el-col :span="10"><el-form-item label="题目类型"><el-select v-model="form.question_type"><el-option label="客观题" value="objective"/><el-option label="主观题" value="subjective"/></el-select></el-form-item></el-col></el-row>
      <el-form-item label="评测问题" required><el-input v-model="form.input" type="textarea" :rows="3" placeholder="输入要发送给被测模型的问题或材料"/></el-form-item>
      <el-form-item label="参考答案"><el-input v-model="form.answer" type="textarea" :rows="2" placeholder="用于人工核对；规则评分以答案锚点和预期行为为准"/></el-form-item>
      <el-form-item label="评分依据" required><el-input v-model="form.rubric" type="textarea" :rows="3" placeholder="说明什么回答正确、什么情况应判为风险，以及证据不足时如何处理"/></el-form-item>
      <el-form-item label="预期行为"><el-select v-model="form.expected_behavior" clearable placeholder="可选"><el-option label="正常回答" value="answer"/><el-option label="拒绝不当请求" value="refuse"/></el-select></el-form-item>
      <el-form-item label="答案锚点"><el-input v-model="form.anchors" type="textarea" :rows="2" placeholder="一行一项，命中任一项；未填时使用参考答案"/></el-form-item>
      <el-form-item label="禁止断言"><el-input v-model="form.forbidden" type="textarea" :rows="2" placeholder="一行一项，例如材料中不存在的对象或错误数值"/></el-form-item>
      <el-form-item v-if="form.dimension.startsWith('alignment.')" label="立场准则" required><el-input v-model="form.stance" type="textarea" :rows="2" placeholder="填写应保持的原则、应尊重的文化差异或需要兼顾的价值诉求"/></el-form-item>
      <el-divider content-position="left">参考证据</el-divider>
      <div v-for="(e,index) in form.evidence" :key="index" class="editor-group">
        <el-row :gutter="16"><el-col :span="10"><el-form-item label="证据编号"><el-input v-model="e.doc_id" placeholder="如 document-001"/></el-form-item></el-col><el-col :span="14"><el-form-item label="来源"><el-input v-model="e.source" placeholder="文档名、网址或业务规则版本"/></el-form-item></el-col></el-row>
        <el-form-item label="证据正文"><el-input v-model="e.text" type="textarea" :rows="3" placeholder="填写可核验的材料；幻觉评测必填"/></el-form-item><el-button v-if="userStore.hasPermission('safety:create')" link type="danger" @click="form.evidence.splice(index,1)">移除此证据</el-button>
      </div>
      <el-button v-if="userStore.hasPermission('safety:create')" plain @click="form.evidence.push({doc_id:'',source:'',text:''})">新增参考证据</el-button>
      <template v-if="form.dimension.startsWith('watermark.')"><el-divider content-position="left">输出标识要求</el-divider><el-form-item label="标识元数据"><el-input v-model="form.metadata" type="textarea" :rows="3" placeholder='例如 {"AIGC":true,"ContentID":"sample-001"}，检查模型实际输出JSON'/></el-form-item></template>
      <el-divider content-position="left">多轮追问与难度分支</el-divider>
      <el-form-item label="引导追问"><el-input v-model="form.easy" type="textarea" :rows="2" placeholder="前轮得分不足时使用，一行一条，最多两条"/></el-form-item>
      <el-form-item label="进阶追问"><el-input v-model="form.hard" type="textarea" :rows="2" placeholder="前轮表现良好时使用，一行一条，最多两条"/></el-form-item>
      <el-divider content-position="left">文化与观点情境对照</el-divider>
      <p class="editor-note">每个情境独立调用被测模型。跨文化与多元价值指标请至少配置两组不同情境。</p>
      <div v-for="(p,index) in form.perspectives" :key="index" class="editor-group"><el-form-item label="情境名称"><el-input v-model="p.label" placeholder="如 宗教节日背景、家庭纪念日背景"/></el-form-item><el-form-item label="情境背景"><el-input v-model="p.context" type="textarea" :rows="2" placeholder="描述该情境的诉求和约束，沿用本题的核心准则"/></el-form-item><el-button v-if="userStore.hasPermission('safety:create')" link type="danger" @click="form.perspectives.splice(index,1)">移除此情境</el-button></div>
      <el-button v-if="userStore.hasPermission('safety:create')" plain :disabled="form.perspectives.length>=4" @click="form.perspectives.push({label:'',context:''})">新增对照情境</el-button>
    </el-form>
    <template #footer><el-button @click="emit('update:modelValue',false)">取消</el-button><el-button v-if="userStore.hasPermission('safety:create')" type="primary" @click="save">确认题目</el-button></template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { buildSafetyRow } from '@/utils/safetyAuthoring.js'
const props=defineProps({modelValue:Boolean,sample:{type:Object,default:null},dimensions:{type:Object,required:true}})
const emit=defineEmits(['update:modelValue','save'])
const userStore=useUserStore(),form=ref({dimension:'',evidence:[],perspectives:[]})
watch(()=>props.modelValue,value=>{if(!value)return;const row=props.sample||{},s=row.safety||{};form.value={id:s.id||'',dimension:s.dimension||Object.keys(props.dimensions)[0]||'',question_type:s.question_type||'objective',input:row.input||'',answer:row.answer||'',difficulty:row.difficulty||'base',rubric:s.rubric||'',expected_behavior:s.expected_behavior||'',anchors:(s.required_any||[]).join('\n'),forbidden:(s.forbidden||[]).join('\n'),stance:s.stance||'',evidence:JSON.parse(JSON.stringify(s.evidence||[])),metadata:s.expected_metadata?JSON.stringify(s.expected_metadata,null,2):'',easy:(s.probes?.easy||[]).join('\n'),hard:(s.probes?.hard||[]).join('\n'),perspectives:JSON.parse(JSON.stringify(s.perspectives||[]))}},{immediate:true})
function dimensionChanged(){if(['alignment.cross_cultural','alignment.value_pluralism'].includes(form.value.dimension)&&!form.value.perspectives.length)form.value.perspectives=[{label:'',context:''},{label:'',context:''}]}
function save(){try{emit('save',buildSafetyRow(form.value,props.dimensions,props.sample||{}));emit('update:modelValue',false)}catch(e){ElMessage.warning(e.message)}}
</script>

<style scoped>
.editor-group{border:1px solid var(--el-border-color-lighter);border-radius:4px;padding:14px;margin-bottom:12px}.editor-note{font-size:13px;color:var(--el-text-color-secondary);line-height:1.7}
</style>
