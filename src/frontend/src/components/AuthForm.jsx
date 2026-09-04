import { useState } from 'react'

export default function AuthForm({
  actionLabel,
  altActionLabel,
  altActionHref,
  description,
  fields,
  footer,
  onSubmit,
  submitLabel,
  title,
}) {
  const [showPassword, setShowPassword] = useState(false)
  const [formState, setFormState] = useState(
    Object.fromEntries(fields.map((field) => [field.name, ''])),
  )
  const [status, setStatus] = useState({ type: 'idle', message: '' })

  const passwordFieldNames = new Set(['password', 'confirmPassword'])

  const updateField = (name, value) => {
    setFormState((current) => ({ ...current, [name]: value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setStatus({ type: 'idle', message: '' })

    try {
      await onSubmit(formState)
      setStatus({ type: 'success', message: description.successMessage })
    } catch (error) {
      setStatus({
        type: 'error',
        message: error instanceof Error ? error.message : 'Request failed',
      })
    }
  }

  return (
    <section className="auth-page" aria-label={title}>
      <div className="auth-card">
        <div className="login-header">
          <div>
            <p className="panel-kicker">Tradelens</p>
            <h2>{title}</h2>
          </div>
          <p className="panel-subtitle">{description.subtitle}</p>
        </div>

        <div className="auth-actions">
          <button type="button" className="secondary-button">
            Continue with Google
          </button>
          <button type="button" className="secondary-button secondary-quiet">
            {actionLabel}
          </button>
        </div>

        <div className="divider">
          <span>{description.dividerLabel}</span>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          {fields.map((field) => (
            <label className="field" key={field.name}>
              <span>{field.label}</span>
              {passwordFieldNames.has(field.name) ? (
                <div className="password-row">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    name={field.name}
                    placeholder={field.placeholder}
                    autoComplete={field.autoComplete}
                    value={formState[field.name]}
                    onChange={(event) => updateField(field.name, event.target.value)}
                  />
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-pressed={showPassword}
                  >
                    {showPassword ? 'Hide' : 'Show'}
                  </button>
                </div>
              ) : (
                <input
                  type={field.type}
                  name={field.name}
                  placeholder={field.placeholder}
                  autoComplete={field.autoComplete}
                  value={formState[field.name]}
                  onChange={(event) => updateField(field.name, event.target.value)}
                />
              )}
            </label>
          ))}

          {footer}

          <button type="submit" className="primary-button">
            {submitLabel}
          </button>
        </form>

        {status.type !== 'idle' ? (
          <p className={`form-message ${status.type}`}>{status.message}</p>
        ) : null}

        <p className="auth-switch">
          {description.switchText}{' '}
          <a href={altActionHref} className="link">
            {altActionLabel}
          </a>
        </p>
      </div>
    </section>
  )
}
