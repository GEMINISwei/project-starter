// **不要在這個檔案加上 "use server"。** 這四個泛用 helper 會變成公開端點, 任何人都能拿來打
// **任意**後端路徑 —— 等於把 nginx 刻意關掉的 `/api/` 代理開回來, 而且介面更寬。
// 要開放寫入請在各模組的 actions.ts 包一層具名、窄介面的 Server Action。
import "server-only"

import { revalidatePath, revalidateTag } from "next/cache"
import { cookies, headers } from "next/headers"
import { redirect } from "next/navigation"
import { buildRequestHeaders } from "@/shared/api/headers"
import { getBodyData, parseErrorDetail } from "@/shared/api/payload"
import { isRedirectError } from "@/shared/api/redirect"
import { getLocale } from "@/shared/i18n/locale.server"
import { clearAccessTokenCookie } from "@/shared/session/access-token.server"
import {
  ACCESS_TOKEN_COOKIE,
  LOGIN_REDIRECT_REASONS,
  type LoginRedirectReason,
  loginUrl,
} from "@/shared/session/login-contract"
import type {
  ApiPathsFor,
  ApiResponse,
  ApiSuccessData,
  AuthPolicy,
  DataObject,
  DeleteRequest,
  GetRequest,
  PatchRequest,
  PostRequest,
  RefreshInfo,
  RevalidateInfo,
} from "@/shared/api/contract"

// 呼叫端傳模板路徑 (`/users/{id}`) 與 params, literal url 才推得出 body 與回應的型別。
type PathParamValues = Record<string, string | number>

function resolvePath(template: string, params?: PathParamValues): string {
  if (!params) return template

  return template.replace(/\{(\w+)\}/g, (_match, key: string) => {
    const value = params[key]
    if (value === undefined) {
      // 型別上不該發生, 但比默默送出一個帶著 `{id}` 的網址好追。
      throw new Error(`路徑參數缺少 "${key}"：${template}`)
    }
    return encodeURIComponent(String(value))
  })
}

// 一律回傳字串 (可能是空字串), 讓呼叫端能正確判斷是否需要加上 `?`。
function getQueryString(data: DataObject | undefined): string {
  if (data === undefined) return ""

  const params = new URLSearchParams()

  Object.entries(data).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, String(item)))
    } else {
      params.append(key, String(value))
    }
  })

  return params.toString()
}

// 本模組帶 "server-only", 在測試環境載入不了, 所以純函式一律抽出去以便單元測試:
// getBodyData / parseErrorDetail 在 shared/api/payload.ts, header 組裝在 shared/api/headers.ts。

// **不要把 API_URL 搬進 next.config.ts 的 `env` 區塊**, 那會把內部拓撲內嵌進 client bundle。
const DEFAULT_API_URL = "http://api:8000"

function getApiBaseUrl() {
  return process.env.API_URL || DEFAULT_API_URL
}

async function getToken(): Promise<string | undefined> {
  const cookieStore = await cookies()

  return cookieStore.get(ACCESS_TOKEN_COOKIE)?.value
}

// 拿不到就回 undefined 而不是自己產: 這一層產的 id 對不上任何上游紀錄。
async function getRequestId(): Promise<string | undefined> {
  const headerStore = await headers()

  return headerStore.get("x-request-id") ?? undefined
}

// 後端的限流以它為 key; 不轉傳的話後端只看得到 web 容器的位址。
async function getClientIp(): Promise<string | undefined> {
  const headerStore = await headers()

  // **不要改讀 X-Forwarded-For**, 它可由用戶端偽造。
  return headerStore.get("x-real-ip") ?? undefined
}

async function redirectToLogin(reason?: LoginRedirectReason) {
  try {
    await clearAccessTokenCookie()
  } catch {
    // 刪不掉 cookie 也要繼續導向。Server Component 的算繪階段不允許寫 cookie,
    // 在那裡讓例外往外跑的話, 使用者會停在一個永遠拿 401 的頁面而不是被送回登入頁。
  }

  redirect(loginUrl(reason))
}

function isAuthRequired(request: { auth?: AuthPolicy }) {
  return request.auth !== "none"
}

async function checkAuth(request: { auth?: AuthPolicy }, res?: Response) {
  if (!isAuthRequired(request)) return

  if (!res) {
    const token = await getToken()

    if (!token) {
      await redirectToLogin(LOGIN_REDIRECT_REASONS.sessionExpired)
    }

    return
  }

  if (res.status === 401) {
    await redirectToLogin(LOGIN_REDIRECT_REASONS.sessionExpired)
  }
}

function setRefresh(refresh?: RefreshInfo) {
  if (!refresh) return

  if (refresh.path) {
    revalidatePath(refresh.path)
  }

  if (refresh.tag) {
    revalidateTag(refresh.tag, "max")
  }
}

type RequestOptions = {
  method: "GET" | "POST" | "PATCH" | "DELETE"
  url: string
  auth?: AuthPolicy
  query?: DataObject
  body?: { contentType: "json" | "form-data"; data: DataObject }
  revalidate?: RevalidateInfo
  refresh?: RefreshInfo
  // 只有 POST/PATCH/DELETE 會把 204 當成成功的「無內容」回應; GET 維持原行為,
  // 不特別處理 204 (若後端真的對 GET 回 204, 會落入下方 res.json() 而被 catch 包成 error)。
  noContentMessage?: string
}

/**
 * 組出 `fetch` 的第二個參數: headers、body 與 Next 的快取設定。抽出來是為了讓 `request` 只剩
 * 「送出、判讀回應」的主線; header 組裝再往下一層在 shared/api/headers.ts (純函式, 可測)。
 */
async function buildRequestInit(
  options: RequestOptions,
  token: string | undefined,
): Promise<RequestInit> {
  const config: RequestInit = {
    method: options.method,
    headers: buildRequestHeaders({
      locale: await getLocale(),
      authRequired: isAuthRequired(options),
      token,
      contentType: options.body?.contentType,
      requestId: await getRequestId(),
      clientIp: await getClientIp(),
    }),
  }

  if (options.body) {
    const bodyData = getBodyData(options.body.data)
    if (options.body.contentType === "form-data") {
      config.body = new URLSearchParams(
        Object.entries(bodyData).map(([key, value]) => [key, String(value)])
      )
    } else {
      config.body = JSON.stringify(bodyData)
    }
  }

  if (options.method === "GET") {
    const hasRevalidate = options.revalidate && Object.keys(options.revalidate).length > 0
    config.next = hasRevalidate
      ? { revalidate: options.revalidate?.time, tags: options.revalidate?.tags }
      : { revalidate: 0 }
  }

  return config
}

async function request<T>(options: RequestOptions): Promise<ApiResponse<T>> {
  try {
    const token = await getToken()
    await checkAuth(options)

    const config = await buildRequestInit(options, token)
    const query = getQueryString(options.query)
    const url = `${getApiBaseUrl()}/api${options.url}` + (query ? `?${query}` : "")
    const res = await fetch(url, config)
    await checkAuth(options, res)

    if (res.status === 204 && options.noContentMessage) {
      return {
        status: "info",
        code: 204,
        data: {},
        message: `${options.method} "${options.url}" ${options.noContentMessage}`,
      }
    }

    const resData = await res.json()

    if (res.ok) {
      setRefresh(options.refresh)

      return {
        status: "success",
        code: res.status,
        data: resData as T,
        message: `${options.method} "${options.url}" Success`,
      }
    }

    const { message: errorMessage, fieldErrors } = parseErrorDetail(resData["detail"])

    return {
      status: "failure",
      code: res.status,
      data: { detail: errorMessage, ...(fieldErrors ? { fieldErrors } : {}) },
      message: `${options.method} "${options.url}" Failure: ${errorMessage}`,
    }
  } catch (err) {
    if (isRedirectError(err)) {
      throw err
    }

    const e = err as Error
    const message = `${options.method} "${options.url}" Error: ${e.message}`
    const methodLabel = options.method.charAt(0) + options.method.slice(1).toLowerCase()

    return {
      status: "error",
      code: 999,
      data: { detail: `Api ${methodLabel} Server Error` },
      message,
    }
  }
}

// 四個 helper 的回應型別都由 `url` 與 method 推導 (`ApiSuccessData<P, method>`); 呼叫端
// 不需也不能自行指定泛型, 端點與回應形狀會維持一致。

export async function apiGet<P extends ApiPathsFor<"get">>(
  getRequest: GetRequest<P>
): Promise<ApiResponse<ApiSuccessData<P, "get">>> {
  return request<ApiSuccessData<P, "get">>({
    method: "GET",
    url: resolvePath(getRequest.url, getRequest.params as PathParamValues | undefined),
    auth: getRequest.auth,
    query: getRequest.query as DataObject | undefined,
    revalidate: getRequest.revalidate,
  })
}

export async function apiPost<P extends ApiPathsFor<"post">>(
  postRequest: PostRequest<P>
): Promise<ApiResponse<ApiSuccessData<P, "post">>> {
  return request<ApiSuccessData<P, "post">>({
    method: "POST",
    url: resolvePath(postRequest.url, postRequest.params as PathParamValues | undefined),
    auth: postRequest.auth,
    body: {
      contentType: postRequest.contentType ?? "json",
      data: (postRequest.data ?? {}) as DataObject,
    },
    refresh: postRequest.refresh,
    noContentMessage: "No Content",
  })
}

export async function apiPatch<P extends ApiPathsFor<"patch">>(
  patchRequest: PatchRequest<P>
): Promise<ApiResponse<ApiSuccessData<P, "patch">>> {
  return request<ApiSuccessData<P, "patch">>({
    method: "PATCH",
    url: resolvePath(patchRequest.url, patchRequest.params as PathParamValues | undefined),
    auth: patchRequest.auth,
    body: { contentType: "json", data: (patchRequest.data ?? {}) as DataObject },
    refresh: patchRequest.refresh,
    noContentMessage: "No Change",
  })
}

export async function apiDelete<P extends ApiPathsFor<"delete">>(
  deleteRequest: DeleteRequest<P>
): Promise<ApiResponse<ApiSuccessData<P, "delete">>> {
  return request<ApiSuccessData<P, "delete">>({
    method: "DELETE",
    url: resolvePath(deleteRequest.url, deleteRequest.params as PathParamValues | undefined),
    auth: deleteRequest.auth,
    query: deleteRequest.query as DataObject | undefined,
    refresh: deleteRequest.refresh,
    noContentMessage: "No Content",
  })
}
