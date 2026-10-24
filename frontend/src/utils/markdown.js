import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: false })
markdown.renderer.rules.table_open = () => '<div class="markdown-table"><table>'
markdown.renderer.rules.table_close = () => '</table></div>'
const defaultLink = markdown.renderer.rules.link_open || ((tokens, index, options, env, renderer) => renderer.renderToken(tokens, index, options))
markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return defaultLink(tokens, index, options, env, renderer)
}
export function renderMarkdown(content) {
  return DOMPurify.sanitize(markdown.render(String(content || '')), { USE_PROFILES: { html: true }, ADD_ATTR: ['target'] })
}
