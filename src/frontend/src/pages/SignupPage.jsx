import AuthForm from '../components/AuthForm.jsx'
import { register } from '../api/authApi.js'

import React from 'react'

const signupFields = [
  {
    name: 'email',
    label: 'Email address',
    type: 'email',
    placeholder: 'name@company.com',
    autoComplete: 'email',
  },
  {
    name: 'password',
    label: 'Password',
    type: 'password',
    placeholder: 'Create a password',
    autoComplete: 'new-password',
  },
  {
    name: 'confirmPassword',
    label: 'Confirm password',
    type: 'password',
    placeholder: 'Repeat your password',
    autoComplete: 'new-password',
  },
]

export default function SignupPage({ onRegistered }) {
  return (
    <main className="login-shell login-shell--signup">
      <section className="signup-aside" aria-hidden="true">
        <p className="eyebrow">Create access</p>
        <h1>Open an account and start tracking the close.</h1>
        <p className="hero-description">
          Registration feeds the same API the login page uses, with reusable
          form pieces and a postgres-backed repository in the backend.
        </p>

        <div className="signup-notes">
          <article>
            <strong>Reusable form</strong>
            <p>Shared fields and actions keep the auth UI consistent.</p>
          </article>
          <article>
            <strong>API first</strong>
            <p>Registration posts to <code>/api/register</code>.</p>
          </article>
          <article>
            <strong>Testable backend</strong>
            <p>Repository and service are injected into the HTTP handler.</p>
          </article>
        </div>
      </section>

      <AuthForm
        title="Create your account."
        description={{
          subtitle: 'Register with email and password',
          dividerLabel: 'or sign up with email',
          switchText: 'Already have an account?',
          successMessage: 'Registration completed.',
        }}
        actionLabel="Email sign-up link"
        altActionLabel="Sign in"
        altActionHref="/"
        fields={signupFields}
        submitLabel="Create account"
        footer={null}
        onSubmit={async (values) => {
          if (!values.email || !values.password || !values.confirmPassword) throw new Error('Complete all registration fields.')
          if (values.password !== values.confirmPassword) throw new Error('Passwords do not match.')
          await register(values)
          onRegistered()
        }}
      />
    </main>
  )
}
