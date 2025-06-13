import crypto from 'crypto'
import { prisma } from './prisma'

export async function generateVerificationToken(email: string, userId?: string) {
  const token = crypto.randomBytes(32).toString('hex')
  const expires = new Date(Date.now() + 24 * 60 * 60 * 1000) // 24 hours
  
  await prisma.verificationToken.create({
    data: {
      identifier: email,
      token,
      expires,
      userId,
    },
  })
  
  return token
}

export async function verifyToken(token: string) {
  const verificationToken = await prisma.verificationToken.findUnique({
    where: { token },
    include: { user: true },
  })
  
  if (!verificationToken) {
    return { error: 'Invalid token' }
  }
  
  if (verificationToken.expires < new Date()) {
    await prisma.verificationToken.delete({
      where: { token },
    })
    return { error: 'Token expired' }
  }
  
  return { success: true, email: verificationToken.identifier, user: verificationToken.user }
}