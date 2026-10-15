import { useState } from 'react'

type Profile = {
  id: string
  display_name: string
  email: string
  location_consent: boolean
  created_at: string
}

function SignupForm() {
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [locationConsent, setLocationConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [profile, setProfile] = useState<Profile | null>(null)

  async function submit() {
    setError(null)
    setSubmitting(true)
    try {
      const res = await fetch('/api/v1/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: displayName,
          email,
          password,
          location_consent: locationConsent,
        }),
      })
      const body = await res.json()
      if (!res.ok) {
        // Stay on the sign-up form and show why it failed.
        setError(body.error?.message ?? 'Sign up failed')
        return
      }
      setProfile(body)
    } catch {
      setError('Could not reach the server')
    } finally {
      setSubmitting(false)
    }
  }

  if (profile) {
    return (
      <p>
        Account created for {profile.email}. Check your inbox to confirm your
        email, then sign in.
      </p>
    )
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      <h1>Sign up</h1>
      <label>
        Display name
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          required
        />
      </label>
      <label>
        Email
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </label>
      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={6}
          required
        />
      </label>
      <label>
        <input
          type="checkbox"
          checked={locationConsent}
          onChange={(e) => setLocationConsent(e.target.checked)}
        />
        Allow location tracking during activities
      </label>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Signing up…' : 'Sign up'}
      </button>
    </form>
  )
}

export default SignupForm
