import React, { useEffect, useState } from 'react'
import { updateProfile } from '../api/profileApi.js'
import { THEMES, normalizeTheme } from '../themePreferences.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'

export default function ProfilePage({ user, theme, onThemeChange, onProfileUpdated, onUnauthorized }) {
  useDocumentTitle('Profile')
  const [selectedTheme, setSelectedTheme] = useState(normalizeTheme(user?.theme || theme))
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => setSelectedTheme(normalizeTheme(user?.theme || theme)), [user?.theme, theme])

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const payload = await updateProfile({ theme: selectedTheme }, { onUnauthorized })
      onThemeChange(payload.user.theme)
      onProfileUpdated(payload.user)
      setMessage('Your appearance preference has been saved.')
    } catch (requestError) {
      if (requestError.status !== 401) setError(requestError.message || 'Could not save your profile.')
    } finally {
      setSaving(false)
    }
  }

  return <section className="profile-page" aria-labelledby="profile-title">
    <header className="page-intro">
      <div><h1 id="profile-title">Profile</h1></div>
    </header>
    <div className="profile-layout">
      <section className="surface-card profile-account" aria-labelledby="account-heading">
        <h2 id="account-heading">Account</h2>
        <dl><div><dt>Email</dt><dd>{user?.email}</dd></div><div><dt>Access</dt><dd>{user?.isAdmin || user?.is_admin ? 'Administrator' : 'Member'}</dd></div></dl>
      </section>
      <form className="surface-card profile-appearance" onSubmit={save}>
        <div className="section-heading"><div><h2>Theme</h2></div></div>
        <fieldset className="theme-grid"><legend className="visually-hidden">Theme selection</legend>
          {THEMES.map((option) => <label className={`theme-option theme-option--${option.id}`} key={option.id}>
            <input type="radio" name="theme" value={option.id} checked={selectedTheme === option.id} onChange={() => { setSelectedTheme(option.id); onThemeChange(option.id) }} />
            <span className="theme-preview" aria-hidden="true"><i /><i /><i /></span>
            <span><strong>{option.name}</strong><small>{option.description}</small></span>
          </label>)}
        </fieldset>
        {error && <p className="form-error" role="alert">{error}</p>}
        {message && <p className="form-success" role="status">{message}</p>}
        <div className="profile-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save preference'}</button></div>
      </form>
    </div>
  </section>
}
