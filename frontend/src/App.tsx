import React, { useState, useEffect } from 'react'

interface Receipt {
  id: string
  supplier_name?: string
  total_amount: number
  currency: string
  status: string
  confidence_score: number
}

export default function App() {
  const [receipts, setReceipts] = useState<Receipt[]>([])
  const [health, setHealth] = useState<string>('Checking...')

  useEffect(() => {
    fetch('/api/health/live')
      .then(res => res.json())
      .then(data => setHealth(data.status))
      .catch(() => setHealth('offline'))

    fetch('/api/receipts')
      .then(res => res.json())
      .then(data => setReceipts(data))
      .catch(() => {})
  }, [])

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
      <header style={{ borderBottom: '1px solid #ccc', paddingBottom: '1rem', marginBottom: '1.5rem' }}>
        <h1>Restaurant Expense & OCR Platform</h1>
        <p>API Status: <strong style={{ color: health === 'healthy' ? 'green' : 'red' }}>{health}</strong></p>
      </header>

      <section style={{ marginBottom: '2rem' }}>
        <h2>Upload Supplier Invoice</h2>
        <input type="file" accept="image/*,.pdf" />
        <button style={{ marginLeft: '1rem', padding: '0.5rem 1rem' }}>Upload & Extract</button>
      </section>

      <section>
        <h2>Recent Supplier Receipts</h2>
        {receipts.length === 0 ? (
          <p>No receipts processed yet.</p>
        ) : (
          <ul>
            {receipts.map(r => (
              <li key={r.id}>
                <strong>{r.supplier_name || 'Processing...'}</strong> — {r.total_amount} {r.currency} [{r.status}]
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
