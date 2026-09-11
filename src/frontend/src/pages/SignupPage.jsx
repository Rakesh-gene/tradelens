import AuthForm from '../components/AuthForm.jsx'
import SiteFooter from '../components/SiteFooter.jsx'
import { register } from '../api/authApi.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'

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
  useDocumentTitle('Create account')
  return (
    <div className="public-shell">
    <main className="login-shell login-shell--signup">
      <section className="signup-aside" aria-hidden="true">
        <h1>Create your TradeLens account.</h1>
        <p className="hero-description">Access market setups, evidence, and risk levels.</p>
      </section>

      <AuthForm
        title="Create your account."
        description={{
          subtitle: 'Register with email and password',
          switchText: 'Already have an account?',
          successMessage: 'Registration completed.',
        }}
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
    <SiteFooter />
    </div>
  )
}
