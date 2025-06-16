import nodemailer from 'nodemailer'

const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST,
  port: parseInt(process.env.SMTP_PORT || '587'),
  secure: process.env.SMTP_SECURE === 'true',
  auth: process.env.SMTP_USER && process.env.SMTP_PASSWORD ? {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASSWORD,
  } : undefined,
})

export async function sendVerificationEmail(email: string, token: string) {
  const verificationUrl = `${process.env.NEXT_PUBLIC_APP_URL}/auth/verify-email?token=${token}`
  
  const mailOptions = {
    from: process.env.SMTP_FROM || 'noreply@example.com',
    to: email,
    subject: 'Verify your email address',
    html: `
      <h1>Verify your email</h1>
      <p>Click the link below to verify your email address:</p>
      <a href="${verificationUrl}">Verify Email</a>
      <p>Or copy and paste this URL into your browser:</p>
      <p>${verificationUrl}</p>
      <p>This link will expire in 24 hours.</p>
    `,
  }
  
  // Development mode: Log to console instead of sending
  if (process.env.NODE_ENV === 'development' || !process.env.SMTP_HOST || process.env.SMTP_HOST === 'smtp.gmail.com' && process.env.SMTP_PASSWORD === 'your-app-password') {
    console.log('\n📧 EMAIL DEBUG (Development Mode):')
    console.log('To:', email)
    console.log('Subject:', mailOptions.subject)
    console.log('Verification URL:', verificationUrl)
    console.log('---\n')
    return
  }
  
  await transporter.sendMail(mailOptions)
}

export async function sendPasswordResetEmail(email: string, token: string) {
  const resetUrl = `${process.env.NEXT_PUBLIC_APP_URL}/auth/reset-password?token=${token}`
  
  const mailOptions = {
    from: process.env.SMTP_FROM || 'noreply@example.com',
    to: email,
    subject: 'Reset your password',
    html: `
      <h1>Reset your password</h1>
      <p>Click the link below to reset your password:</p>
      <a href="${resetUrl}">Reset Password</a>
      <p>Or copy and paste this URL into your browser:</p>
      <p>${resetUrl}</p>
      <p>This link will expire in 1 hour.</p>
    `,
  }
  
  // Development mode: Log to console instead of sending
  if (process.env.NODE_ENV === 'development' || !process.env.SMTP_HOST || process.env.SMTP_HOST === 'smtp.gmail.com' && process.env.SMTP_PASSWORD === 'your-app-password') {
    console.log('\n📧 EMAIL DEBUG (Development Mode):')
    console.log('To:', email)
    console.log('Subject:', mailOptions.subject)
    console.log('Reset URL:', resetUrl)
    console.log('---\n')
    return
  }
  
  await transporter.sendMail(mailOptions)
}