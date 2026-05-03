import { postMultipart, request } from './http'

export type IngestJobStep = {
  step_key: string
  status: string
  item_count: number | null
  detail: string | null
}

export type IngestJob = {
  id: string
  job_type: string
  status: string
  account_id: string
  statement_id: string | null
  filename: string
  byte_size: number
  parsed_rows: number | null
  inserted_rows: number | null
  skipped_duplicates: number | null
  error_detail: string | null
  retry_count: number
  steps: IngestJobStep[]
}

export function enqueueCsvImport(accountId: string, file: File): Promise<IngestJob> {
  const form = new FormData()
  form.set('account_id', accountId)
  form.set('file', file)
  return postMultipart<IngestJob>('/ingest/jobs/csv', form)
}

export function enqueuePdfImport(accountId: string, file: File): Promise<IngestJob> {
  const form = new FormData()
  form.set('account_id', accountId)
  form.set('file', file)
  return postMultipart<IngestJob>('/ingest/jobs/pdf', form)
}

export function getIngestJob(jobId: string): Promise<IngestJob> {
  return request<IngestJob>(`/ingest/jobs/${jobId}`)
}

const TERMINAL_JOB_STATUSES = new Set(['succeeded', 'failed', 'needs_review'])

export async function pollIngestJob(
  jobId: string,
  intervalMs = 500,
  timeoutMs = 30_000,
): Promise<IngestJob> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const job = await getIngestJob(jobId)
    if (TERMINAL_JOB_STATUSES.has(job.status)) return job
    await new Promise<void>(resolve => setTimeout(resolve, intervalMs))
  }
  throw new Error(`Job ${jobId} did not complete within ${timeoutMs / 1000}s — check the jobs list for its current status.`)
}
