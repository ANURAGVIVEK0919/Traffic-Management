/*
 * Frontend request tracer for simulation results flow.
 *
 * Enable by importing once near app startup:
 *   import './debugFrontendFlow'
 */

const TARGET_PATTERNS = ['/simulation/submit-log', '/simulation/results']
const STATE_KEY = '__trafficSimDebugFrontendFlow__'

function getState() {
  if (typeof window === 'undefined') {
    return null
  }

  if (!window[STATE_KEY]) {
    window[STATE_KEY] = {
      enabled: false,
      postSessionId: null,
      postAt: null,
      firstGetAt: null,
      getCount: 0,
      lastGetSessionId: null,
      lastGetUrl: null,
      rootCause: null,
      originalFetch: null,
      originalAxiosRequest: null,
    }
  }

  return window[STATE_KEY]
}

function isoNow() {
  return new Date().toISOString()
}

function formatClock(isoString) {
  if (!isoString) return 'n/a'
  return new Date(isoString).toLocaleTimeString()
}

function safeJsonStringify(value) {
  try {
    return JSON.stringify(value)
  } catch {
    return '[unserializable body]'
  }
}

function isTargetUrl(url) {
  return TARGET_PATTERNS.some((pattern) => url.includes(pattern))
}

function extractSessionIdFromUrl(url) {
  try {
    const parsed = new URL(url, window.location.origin)
    return parsed.searchParams.get('session_id') || parsed.searchParams.get('sessionId') || parsed.pathname.split('/').filter(Boolean).slice(-1)[0] || null
  } catch {
    return null
  }
}

function extractSessionIdFromBody(body) {
  if (!body) return null

  if (typeof body === 'string') {
    try {
      const parsed = JSON.parse(body)
      return extractSessionIdFromBody(parsed)
    } catch {
      return null
    }
  }

  if (body instanceof URLSearchParams) {
    return body.get('session_id') || body.get('sessionId') || null
  }

  if (body instanceof FormData) {
    return body.get('session_id') || body.get('sessionId') || null
  }

  if (body && typeof body === 'object') {
    return body.session_id || body.sessionId || body.sessionID || null
  }

  return null
}

function logRequest({ endpoint, method, sessionId, url, body }) {
  console.log(`[REQUEST] endpoint=${endpoint}`)
  console.log(`[REQUEST] method=${method}`)
  console.log(`[REQUEST] session_id=${sessionId || 'n/a'}`)
  console.log(`[REQUEST] timestamp=${isoNow()}`)
  if (body !== undefined) {
    console.log(`[REQUEST] body=${safeJsonStringify(body)}`)
  }
  if (url) {
    console.log(`[REQUEST] url=${url}`)
  }
}

async function readResponseBody(response) {
  const contentType = response.headers?.get?.('content-type') || ''
  try {
    if (contentType.includes('application/json')) {
      return await response.clone().json()
    }
    return await response.clone().text()
  } catch (error) {
    return `[failed to read body: ${error?.message || error}]`
  }
}

function updateRootCause(state, nextCause) {
  if (!state.rootCause) {
    state.rootCause = nextCause
  }
}

function finalizeDiagnosis(state) {
  const postSessionId = state.postSessionId
  const firstGetSessionId = state.lastGetSessionId
  const firstGetAt = state.firstGetAt
  const postAt = state.postAt

  if (!postSessionId || !firstGetSessionId) {
    return state.rootCause || 'ROOT CAUSE: UNKNOWN'
  }

  if (postSessionId !== firstGetSessionId) {
    return 'ROOT CAUSE: SESSION ID MISMATCH'
  }

  if (postAt && firstGetAt) {
    const deltaMs = firstGetAt - postAt
    if (deltaMs < 300) {
      return 'ROOT CAUSE: TIMING ISSUE (GET too early)'
    }
  }

  if (state.getCount > 1) {
    return 'ROOT CAUSE: MULTIPLE RETRIES BEFORE SAVE'
  }

  return state.rootCause || 'ROOT CAUSE: UNKNOWN'
}

function logResponse({ endpoint, response, body }) {
  console.log(`[RESPONSE] endpoint=${endpoint}`)
  console.log(`[RESPONSE] status=${response.status}`)
  console.log(`[RESPONSE] timestamp=${isoNow()}`)
  console.log(`[RESPONSE] body=${safeJsonStringify(body)}`)

  const bodyText = typeof body === 'string' ? body : safeJsonStringify(body)
  if (bodyText.includes('Results not ready')) {
    console.log('Backend says results not ready')
  }
}

function installFetchTracer() {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') {
    return
  }

  const state = getState()
  if (!state || state.enabled) {
    return
  }

  state.enabled = true
  state.originalFetch = window.fetch.bind(window)

  window.fetch = async function debugFrontendFetch(input, init = {}) {
    const requestUrl = typeof input === 'string'
      ? input
      : input?.url || String(input)
    const requestMethod = (init.method || input?.method || 'GET').toUpperCase()
    const requestBody = init.body ?? input?.body ?? null
    const endpoint = isTargetUrl(requestUrl) ? requestUrl : null

    if (!endpoint) {
      return state.originalFetch(input, init)
    }

    const sessionId = requestMethod === 'POST'
      ? extractSessionIdFromBody(requestBody)
      : extractSessionIdFromUrl(requestUrl)

    if (requestMethod === 'POST' && requestUrl.includes('/simulation/submit-log')) {
      state.postSessionId = sessionId || state.postSessionId
      state.postAt = Date.now()
      state.firstGetAt = null
      state.getCount = 0
      state.lastGetSessionId = null
      state.lastGetUrl = null
      state.rootCause = null
    }

    if (requestMethod === 'GET' && requestUrl.includes('/simulation/results')) {
      state.getCount += 1
      console.log(`Retry attempt #${state.getCount}`)
      if (!state.firstGetAt) {
        state.firstGetAt = Date.now()
      }
      state.lastGetSessionId = sessionId
      state.lastGetUrl = requestUrl

      if (state.postSessionId && sessionId && state.postSessionId !== sessionId) {
        console.log('❌ SESSION ID MISMATCH')
        updateRootCause(state, 'ROOT CAUSE: SESSION ID MISMATCH')
      }

      if (state.postAt && state.firstGetAt) {
        const deltaMs = state.firstGetAt - state.postAt
        console.log(`Time from POST to first GET: ${deltaMs}ms`)
        if (deltaMs < 300) {
          console.log('WARNING: GET called too early (possible timing issue)')
          updateRootCause(state, 'ROOT CAUSE: TIMING ISSUE (GET too early)')
        }
      }

      if (state.getCount > 1) {
        updateRootCause(state, 'ROOT CAUSE: MULTIPLE RETRIES BEFORE SAVE')
      }
    }

    logRequest({
      endpoint: requestUrl,
      method: requestMethod,
      sessionId,
      url: requestUrl,
      body: requestMethod === 'POST' ? requestBody : undefined,
    })

    try {
      const response = await state.originalFetch(input, init)
      const responseBody = await readResponseBody(response)

      logResponse({
        endpoint: requestUrl,
        response,
        body: responseBody,
      })

      if (requestMethod === 'GET' && requestUrl.includes('/simulation/results')) {
        const bodyText = typeof responseBody === 'string' ? responseBody : safeJsonStringify(responseBody)
        if (bodyText.includes('Results not ready')) {
          console.log('Backend says results not ready')
          updateRootCause(state, 'ROOT CAUSE: TIMING ISSUE (GET too early)')
        }
      }

      if (state.getCount > 1 && !state.rootCause) {
        updateRootCause(state, 'ROOT CAUSE: MULTIPLE RETRIES BEFORE SAVE')
      }

      if (!state.rootCause && state.postSessionId && state.lastGetSessionId && state.postSessionId !== state.lastGetSessionId) {
        updateRootCause(state, 'ROOT CAUSE: SESSION ID MISMATCH')
      }

      console.log(`ROOT CAUSE: ${finalizeDiagnosis(state).replace('ROOT CAUSE: ', '')}`)
      return response
    } catch (error) {
      console.log(`[RESPONSE] endpoint=${requestUrl}`)
      console.log(`[RESPONSE] status=network-error`)
      console.log(`[RESPONSE] timestamp=${isoNow()}`)
      console.log(`[RESPONSE] body=${error?.message || error}`)
      throw error
    }
  }
}

function installAxiosTracer() {
  if (typeof window === 'undefined') {
    return
  }

  const axios = window.axios
  if (!axios || axios.__trafficSimDebugPatched) {
    return
  }

  const state = getState()
  if (!state) {
    return
  }

  axios.__trafficSimDebugPatched = true

  if (typeof axios.interceptors?.request?.use === 'function' && typeof axios.interceptors?.response?.use === 'function') {
    axios.interceptors.request.use((config) => {
      const requestUrl = config?.url || ''
      if (!isTargetUrl(requestUrl)) {
        return config
      }

      const method = String(config.method || 'get').toUpperCase()
      const sessionId = method === 'POST'
        ? extractSessionIdFromBody(config.data)
        : extractSessionIdFromUrl(requestUrl)

      logRequest({
        endpoint: requestUrl,
        method,
        sessionId,
        url: requestUrl,
        body: config.data,
      })

      return config
    })

    axios.interceptors.response.use((response) => {
      const requestUrl = response?.config?.url || ''
      if (isTargetUrl(requestUrl)) {
        Promise.resolve(readResponseBody(response)).then((body) => {
          logResponse({ endpoint: requestUrl, response, body })
        })
      }
      return response
    }, (error) => {
      const requestUrl = error?.config?.url || ''
      if (isTargetUrl(requestUrl)) {
        console.log(`[RESPONSE] endpoint=${requestUrl}`)
        console.log('[RESPONSE] status=network-error')
        console.log(`[RESPONSE] timestamp=${isoNow()}`)
        console.log(`[RESPONSE] body=${error?.message || error}`)
      }
      return Promise.reject(error)
    })
  }
}

installFetchTracer()
installAxiosTracer()

export function getDebugFrontendFlowState() {
  return getState()
}

export function resetDebugFrontendFlowState() {
  const state = getState()
  if (!state) return
  state.postSessionId = null
  state.postAt = null
  state.firstGetAt = null
  state.getCount = 0
  state.lastGetSessionId = null
  state.lastGetUrl = null
  state.rootCause = null
}
