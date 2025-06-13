import { Queue, Worker, Job } from 'bullmq'
import Redis from 'ioredis'

// Create Redis connection
const connection = new Redis(process.env.REDIS_URL || 'redis://localhost:6379', {
  maxRetriesPerRequest: null,
})

// Define queue names
export const QUEUES = {
  EMAIL: 'email',
  FILE_PROCESSING: 'file-processing',
  WEBHOOK: 'webhook',
} as const

// Create queues
export const emailQueue = new Queue(QUEUES.EMAIL, { connection })
export const fileProcessingQueue = new Queue(QUEUES.FILE_PROCESSING, { connection })
export const webhookQueue = new Queue(QUEUES.WEBHOOK, { connection })

// Queue job types
export interface EmailJob {
  to: string
  subject: string
  html: string
  from?: string
}

export interface FileProcessingJob {
  userId: string
  fileKey: string
  operation: 'resize' | 'compress' | 'convert'
  options?: Record<string, any>
}

export interface WebhookJob {
  url: string
  method: 'POST' | 'PUT'
  data: any
  headers?: Record<string, string>
}