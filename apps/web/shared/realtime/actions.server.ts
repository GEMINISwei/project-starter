"use server"

import { apiPost } from "@/shared/api/request.server"

export async function requestWsTicket(): Promise<string | null> {
  const res = await apiPost({ url: "/ws/ticket" })
  return res.status === "success" ? res.data.ticket : null
}
