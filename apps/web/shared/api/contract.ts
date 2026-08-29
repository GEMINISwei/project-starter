// API 層的共用型別，一律具名 export，讓每個使用點都明確標示來源。
//
// Entity 型別（UserInfo、RoleInfo…）不在這裡，一律從 `@/shared/api/entities` 取得。

import type { paths } from "./generated/schema"

export type DataValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | DataObject
  | DataValue[]

export type DataObject = {
  [key: string]: DataValue
}

/** 失敗回應的 payload。`detail` 一律有值（後端 LangException 的訊息或前端的 fallback）。 */
export type ApiErrorData = {
  detail: string
  /**
   * 欄位級驗證錯誤（HTTP 422）。key 是欄位路徑（例如 `body → password`）。
   * 後端 RequestValidationError handler 會回傳完整陣列，`request.server.ts` 把它攤平到這裡，
   * 讓表單能把錯誤標在對應欄位上，而不是只有一句籠統的訊息。
   */
  fieldErrors?: Record<string, string>
}

/**
 * API 回應的辨識聯集。用 `status` 當 discriminant，因此：
 *
 *   const res = await apiGet({ url: "/roles/{id}", params: { id } })
 *   if (res.status === "success") res.data.name   // ← 已窄化成 RoleInfo，有型別
 *   else res.data.detail                          // ← 已窄化成 ApiErrorData
 *
 * `T` 由 helper 從 `url` 推導（見下方的 ApiSuccessData），呼叫端不需要、也不應該自己指定。
 */
export type ApiResponse<T = DataObject> =
  | { status: "success"; code: number; data: T; message: string }
  | { status: "info"; code: number; data: Record<string, never>; message: string }
  | { status: "failure" | "error"; code: number; data: ApiErrorData; message: string }

export type RevalidateInfo = {
  time?: number
  tags?: string[]
}

export type RefreshInfo = {
  path?: string
  tag?: string
}

export type AuthPolicy = "required" | "none"

// ---- 由 OpenAPI 推導的請求型別 ----
// 以下型別把 literal url 與 HTTP method 綁到 `generated/schema.d.ts` 的 paths / operations，
// 讓 apiGet / apiPost / apiPatch / apiDelete 在編譯期驗證端點、參數與資料形狀。

/** 後端所有路由都掛在 `/api` 底下，helper 會自己補這個前綴，所以對外的 path 不含它。 */
type StripApiPrefix<T> = T extends `/api${infer Rest}` ? Rest : never

type WithApiPrefix<P extends string> = `/api${P}` extends keyof paths ? `/api${P}` : never

/** 支援 `method` 的所有路徑。用它當呼叫端的 `url` 型別，打錯路徑就是編譯錯誤。 */
export type ApiPathsFor<M extends HttpMethod> = StripApiPrefix<
  {
    [P in keyof paths]: paths[P] extends Record<M, infer Op>
      ? Op extends undefined
        ? never
        : P
      : never
  }[keyof paths]
>

type HttpMethod = "get" | "post" | "patch" | "delete"

type Operation<P extends string, M extends HttpMethod> = WithApiPrefix<P> extends keyof paths
  ? paths[WithApiPrefix<P>] extends Record<M, infer Op>
    ? Op
    : never
  : never

/** 這個端點的成功回應形狀（200 的 application/json）。 */
export type ApiSuccessData<P extends string, M extends HttpMethod> =
  Operation<P, M> extends { responses: { 200: { content: { "application/json": infer R } } } } ? R : never

/** 這個端點的 request body 形狀。沒有 body 的端點（`requestBody?: never`）會是 `never`。 */
type RequestBodyContent<P extends string, M extends HttpMethod> =
  Operation<P, M> extends { requestBody?: infer RB }
    ? RB extends { content: infer C }
      ? C
      : never
    : never

// 兩種 content type 都要處理：JSON 是常態，但 `POST /users/login` 是
// `application/x-www-form-urlencoded`（後端用 FastAPI 的 `Form()` 接）。
// 只看 JSON 的話，登入的 body 會被推成 never，呼叫端反而不能傳 data。
type RequestBody<P extends string, M extends HttpMethod> = [
  RequestBodyContent<P, M>,
] extends [never]
  ? // 必須先明確擋掉 never。`never extends X ? ... : ...` 會走 true 分支，而從 never 裡
    // `infer B` 得到的是 `unknown` —— 於是「沒有 body 的端點」會被推成「body 是 unknown」，
    // 反而變成必填。`POST /ws/ticket` 就是這種端點。
    never
  : RequestBodyContent<P, M> extends { "application/json": infer B }
    ? B
    : RequestBodyContent<P, M> extends { "application/x-www-form-urlencoded": infer B }
      ? B
      : never

/** 路徑參數（`/users/{id}` 的 `{ id }`）。沒有參數的路徑會是 `never`。 */
type PathParams<P extends string, M extends HttpMethod> =
  Operation<P, M> extends { parameters: { path?: infer Params } }
    ? Params extends undefined
      ? never
      : Params
    : never

/** Query 參數。 */
type QueryParams<P extends string, M extends HttpMethod> =
  Operation<P, M> extends { parameters: { query?: infer Q } }
    ? Q extends undefined
      ? never
      : Q
    : never

// 下面三個 helper 讓「沒有這一項的端點」不必傳對應欄位，有的則變成必填。直接寫
// `params?: PathParams<...>` 的話，`never` 會讓欄位變成可選的 never，呼叫端漏傳也不會有錯。
type PathParamsField<P extends string, M extends HttpMethod> = [PathParams<P, M>] extends [never]
  ? { params?: never }
  : { params: PathParams<P, M> }

type QueryField<P extends string, M extends HttpMethod> = [QueryParams<P, M>] extends [never]
  ? { query?: never }
  : { query?: QueryParams<P, M> }

type BodyField<P extends string, M extends HttpMethod> = [RequestBody<P, M>] extends [never]
  ? { data?: never }
  : { data: RequestBody<P, M> }

export type GetRequest<P extends ApiPathsFor<"get">> = {
  url: P
  auth?: AuthPolicy
  revalidate?: RevalidateInfo
} & PathParamsField<P, "get"> &
  QueryField<P, "get">

export type PostRequest<P extends ApiPathsFor<"post">> = {
  url: P
  auth?: AuthPolicy
  contentType?: "json" | "form-data"
  refresh?: RefreshInfo
} & PathParamsField<P, "post"> &
  BodyField<P, "post">

export type PatchRequest<P extends ApiPathsFor<"patch">> = {
  url: P
  auth?: AuthPolicy
  refresh?: RefreshInfo
} & PathParamsField<P, "patch"> &
  BodyField<P, "patch">

// DELETE 也收 query：刪除目標不一定表達得成路徑參數（`DELETE /push/subscriptions` 刪的是
// 瀏覽器給的不透明 endpoint 字串），而帶 body 的 DELETE 不是標準做法。少了這一行，那類端點
// 只能繞過整層自己手寫 fetch，也就繞過了編譯期檢查。
export type DeleteRequest<P extends ApiPathsFor<"delete">> = {
  url: P
  auth?: AuthPolicy
  refresh?: RefreshInfo
} & PathParamsField<P, "delete"> &
  QueryField<P, "delete">

/**
 * Server Action 的 payload 型別，直接由後端 request schema 衍生 —— 後端一改，所有 Server
 * Action 的型別檢查跟著變。
 *
 *     export async function createRole(data: ApiRequestBody<"/roles/", "post">) { … }
 */
export type ApiRequestBody<P extends string, M extends HttpMethod> = RequestBody<P, M>
