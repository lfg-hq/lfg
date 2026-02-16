'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/app/context/AuthContext';
import { buildApiUrl } from '@/app/lib/config';

export default function GoogleCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { completeOAuth } = useAuth();

  const [statusMessage, setStatusMessage] = useState('Connecting your Google account…');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');

    if (!code || !state) {
      setError('Missing authorization details. Please try signing in again.');
      setStatusMessage('');
      return;
    }

    const exchangeCode = async () => {
      try {
        const redirectUri = `${window.location.origin}/auth/google/callback`;
        const response = await fetch(buildApiUrl('auth/google/exchange/'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, state, redirect_uri: redirectUri }),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data?.error || 'Google sign-in failed');
        }

        await completeOAuth({ user: data.user, profile: data.profile ?? null, tokens: data.tokens });
        setStatusMessage('Success! Redirecting to your projects…');
        router.replace('/projects');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to complete Google sign-in');
        setStatusMessage('');
      }
    };

    exchangeCode();
  }, [completeOAuth, router, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-8 text-center space-y-6">
        <div className="flex justify-center">
          <span className="text-4xl">🚀</span>
        </div>
        <h1 className="text-2xl font-semibold text-gray-900">Signing you in…</h1>
        {statusMessage && <p className="text-gray-600">{statusMessage}</p>}
        {error && (
          <div className="space-y-4">
            <p className="text-sm text-red-600">{error}</p>
            <Link
              href="/auth"
              className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700"
            >
              Back to sign in
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
