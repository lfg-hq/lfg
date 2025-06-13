import { Worker, Job } from 'bullmq'
import nodemailer from 'nodemailer'
import { EmailJob, QUEUES } from '@/lib/queue'
import Redis from 'ioredis'

const connection = new Redis(process.env.REDIS_URL || 'redis://localhost:6379', {
  maxRetriesPerRequest: null,
})

const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST,
  port: parseInt(process.env.SMTP_PORT || '587'),
  secure: process.env.SMTP_SECURE === 'true',
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASSWORD,
  },
})

const emailWorker = new Worker<EmailJob>(
  QUEUES.EMAIL,
  async (job: Job<EmailJob>) => {
    const { to, subject, html, from } = job.data
    
    console.log(`Processing email job ${job.id}: sending to ${to}`)
    
    await transporter.sendMail({
      from: from || process.env.SMTP_FROM || 'noreply@example.com',
      to,
      subject,
      html,
    })
    
    console.log(`Email job ${job.id} completed successfully`)
  },
  {
    connection,
    concurrency: 5,
    removeOnComplete: { count: 100 },
    removeOnFail: { count: 100 },
  }
)

emailWorker.on('completed', (job) => {
  console.log(`Email job ${job.id} has completed`)
})

emailWorker.on('failed', (job, err) => {
  console.error(`Email job ${job?.id} has failed with error: ${err.message}`)
})

export default emailWorker