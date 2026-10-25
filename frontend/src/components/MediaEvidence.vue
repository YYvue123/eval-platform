<template>
  <div v-if="media?.length" class="media-evidence">
    <figure v-for="(entry,index) in media" :key="entry.sha256 || index">
      <div v-if="safeImage(entry.data_url)" class="image-frame">
        <el-image :src="entry.data_url" :alt="entry.name || '原始评测图片'" :preview-src-list="[entry.data_url]" fit="contain" class="original-image" />
        <svg v-if="entry.regions?.length" class="region-overlay" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="参考证据区域">
          <rect v-for="(region,i) in entry.regions" :key="i" :x="region.box[0]" :y="region.box[1]" :width="region.box[2]-region.box[0]" :height="region.box[3]-region.box[1]" />
        </svg>
      </div>
      <audio v-if="entry.modality==='audio' && safeMedia(entry.data_url)" :ref="el=>setPlayer(index,el)" :src="entry.data_url" controls preload="metadata" />
      <video v-if="entry.modality==='video' && safeMedia(entry.data_url)" :ref="el=>setPlayer(index,el)" :src="entry.data_url" controls preload="metadata" class="video-player" />
      <figcaption>{{ entry.name || `媒体 ${index+1}` }} · {{ processingName(entry.processing) }}</figcaption>
      <small>SHA256 {{ entry.sha256 }}</small>
      <p v-if="entry.duration_seconds">时长 {{ entry.duration_seconds }} 秒 <span v-if="entry.modality==='video'">· {{ entry.has_audio?'含音轨':'无音轨' }}</span></p>
      <p v-for="(region,i) in entry.regions || []" :key="i">{{ region.label }} · 区域 {{ region.box }}</p>
      <button v-for="(segment,i) in entry.segments || []" :key="`segment-${i}`" v-if="user.hasPermission(permission)" class="segment" @click="seek(index,segment.start)">{{ segment.label || '参考片段' }} {{ segment.start }}–{{ segment.end }} 秒</button>
      <details v-if="entry.frames?.length"><summary>实际发送的 {{ entry.frames.length }} 帧</summary><div v-for="frame in entry.frames" :key="frame.sha256"><small>实际 {{ frame.timestamp_seconds }} 秒（请求 {{ frame.requested_timestamp_seconds ?? frame.timestamp_seconds }} 秒） · {{ frame.sha256 }}</small><img v-if="safeImage(frame.data_url)" :src="frame.data_url" alt="实际发送的视频帧" class="frame-image" /></div><small>抽帧未覆盖连续画面；{{ entry.has_audio?'完整音轨同时发送给被测模型':'本视频无音轨' }}</small></details>
    </figure>
  </div>
</template>
<script setup>
import { useUserStore } from '@/stores/user'
defineProps({ media: { type: Array, default: () => [] }, permission: { type: String, default: 'task:view' } })
const user=useUserStore()
const players=new Map()
const setPlayer=(index,element)=>element?players.set(index,element):players.delete(index)
const seek=(index,time)=>{const player=players.get(index);if(player)player.currentTime=time}
const safeImage = value => /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(value || '')
const safeMedia=value=>/^data:(audio\/(wav|mpeg|mp3)|video\/(mp4|webm));base64,[A-Za-z0-9+/=]+$/.test(value || '')
const processingName=value=>({original_image:'原图输入',original_audio:'原始音频',original_video:'原生视频',sampled_frames:'视频抽帧',sampled_frames_with_audio:'视频抽帧及完整音轨',extracted_audio_track:'提取音轨',model_output_audio:'模型生成音频'}[value] || value || '原始媒体')
</script>
<style scoped>
.media-evidence{display:flex;flex-wrap:wrap;gap:16px}figure{margin:12px 0;max-width:320px;padding:12px;border:1px solid var(--el-border-color-lighter);border-radius:8px;background:var(--el-fill-color-blank)}small{display:block;overflow-wrap:anywhere;color:var(--el-text-color-secondary)}figcaption{margin:8px 0}.image-frame{position:relative;width:240px;max-width:100%}.original-image{display:block;width:100%}.region-overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.region-overlay rect{fill:transparent;stroke:var(--el-color-primary);stroke-width:2;vector-effect:non-scaling-stroke}
.video-player,.frame-image,audio{width:100%;max-width:300px}.segment{display:block;margin:6px 0;padding:6px 10px;border:1px solid var(--el-border-color);border-radius:4px;background:var(--el-fill-color-light);color:var(--el-color-primary);cursor:pointer}details{margin-top:12px}summary{cursor:pointer;color:var(--el-color-primary)}
</style>
