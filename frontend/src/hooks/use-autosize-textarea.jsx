import * as React from "react"

/**
 * Grows a textarea's height to fit its content as the user types, up to
 * maxHeight (px) -- beyond that it scrolls internally instead of growing
 * further, matching standard chat-input UX (ChatGPT, Slack, Intercom).
 * Attach the returned ref to the textarea; it re-measures whenever `value`
 * changes, including external resets (e.g. clearing the input after send).
 */
export function useAutosizeTextarea(value, { minHeight = 40, maxHeight = 160 } = {}) {
  const ref = React.useRef(null)

  React.useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(Math.max(el.scrollHeight, minHeight), maxHeight)}px`
  }, [value, minHeight, maxHeight])

  return ref
}
