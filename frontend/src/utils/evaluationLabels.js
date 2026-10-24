const judges={'builtin/exact_match':'精确匹配','builtin/contains':'关键词包含','builtin/regex':'正则匹配','builtin/fuzzy':'文本相似度','builtin/safety_gen_risk':'生成内容风险检测','builtin/safety_watermark':'合成标识检测','builtin/safety_alignment':'价值对齐评测','builtin/safety_hallucination':'幻觉检测'}
export const judgeLabel=(code,name)=>judges[code] || name || '自定义评测工具'
const packs={'capability.language':'语言能力','capability.speech':'语音能力','capability.vision':'视觉能力','capability.multimodal':'多模态能力','safety.gen_risk':'生成内容风险','safety.watermark':'合成标识','safety.alignment':'价值对齐','safety.hallucination':'幻觉检测'}
const industries={finance:'金融',medical:'医疗',gov:'政务',agriculture:'农业',industry:'工业',power:'电力',petro:'石油石化',mining:'矿山',steel:'钢铁',education:'教育',port:'港口',construction:'建筑',auto:'汽车',legal:'司法'}
export function datasetLabel(name){if(!name?.startsWith('pack:'))return name;const code=name.slice(5);return `内置评测集 · ${packs[code] || industries[code.replace('industry.','')] || '专项能力'}`}
