/**
 * 密码强度与校验：必须字母+数字组合，且大于6位
 */

/** 强度等级 0-4 */
const LEVELS = [
  { level: 0, label: '未设置', type: 'info' },
  { level: 1, label: '弱', type: 'danger' },
  { level: 2, label: '中', type: 'warning' },
  { level: 3, label: '强', type: 'success' },
  { level: 4, label: '很强', type: 'success' }
]

/**
 * 计算密码强度等级 0-4
 * 规则：长度 + 是否含字母 + 是否含数字 + 混合
 */
export function getPasswordStrength(password) {
  if (!password || typeof password !== 'string') return LEVELS[0]
  const pwd = password
  const hasLetter = /[a-zA-Z]/.test(pwd)
  const hasDigit = /\d/.test(pwd)
  const len = pwd.length
  let level = 0
  if (len > 6) level++
  if (hasLetter) level++
  if (hasDigit) level++
  if (hasLetter && hasDigit) level++
  if (level > 4) level = 4
  return LEVELS[level]
}

/**
 * 校验密码是否符合规则：字母与数字组合，且大于6位
 * @returns {{ valid: boolean, message: string }}
 */
export function validatePassword(password) {
  if (!password || typeof password !== 'string') {
    return { valid: false, message: '请输入密码' }
  }
  if (password.length <= 6) {
    return { valid: false, message: '密码必须大于6位' }
  }
  const hasLetter = /[a-zA-Z]/.test(password)
  const hasDigit = /\d/.test(password)
  if (!hasLetter || !hasDigit) {
    return { valid: false, message: '密码必须包含字母和数字' }
  }
  return { valid: true, message: '' }
}
