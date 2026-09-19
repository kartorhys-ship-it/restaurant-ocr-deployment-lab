import React, { useState, useEffect } from 'react'

interface Receipt {
  id: string
  supplier_name?: string
  receipt_number?: string
  receipt_date?: string
  total_amount: number
  currency: string
  status: string
  confidence_score: number
  created_at?: string
}

export default function App() {
  const [receipts, setReceipts] = useState<Receipt[]>([])
  const [health, setHealth] = useState<string>('Checking...')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState<boolean>(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const fetchHealth = () => {
    fetch('/api/health/live')
      .then(res => res.json())
      .then(data => setHealth(data.status))
      .catch(() => setHealth('offline'))
  }

  const fetchReceipts = () => {
    fetch('/api/receipts')
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setReceipts(data)
        }
      })
      .catch(() => {})
  }

  useEffect(() => {
    fetchHealth()
    fetchReceipts()
    const interval = setInterval(fetchReceipts, 3000)
    return () => clearInterval(interval)
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0])
      setStatusMessage(null)
      setErrorMessage(null)
    }
  }

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) {
      setErrorMessage('Please select a receipt scan or invoice file first.')
      return
    }

    setIsUploading(true)
    setStatusMessage('Uploading receipt to server...')
    setErrorMessage(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const res = await fetch('/api/receipts', {
        method: 'POST',
        body: formData
      })

      if (!res.ok) {
        throw new Error(`Upload failed with HTTP status ${res.status}`)
      }

      const data = await res.json()
      setStatusMessage(`Receipt queued successfully! ID: ${data.receipt_id}`)
      setSelectedFile(null)

      // Reset file input element
      const fileInput = document.getElementById('receipt-upload-input') as HTMLInputElement
      if (fileInput) fileInput.value = ''

      fetchReceipts()
    } catch (err: any) {
      setErrorMessage(err.message || 'Error occurred while uploading receipt.')
    } finally {
      setIsUploading(false)
    }
  }

  const handleApprove = async (receiptId: string) => {
    try {
      const res = await fetch(`/api/receipts/${receiptId}/approve`, {
        method: 'POST'
      })
      if (res.ok) {
        fetchReceipts()
      }
    } catch (err) {
      console.error('Approval failed', err)
    }
  }

  return (
    <div style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', padding: '2rem', maxWidth: '840px', margin: '0 auto', color: '#1a202c' }}>
      <header style={{ borderBottom: '1px solid #e2e8f0', paddingBottom: '1rem', marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 600 }}>Restaurant Expense & OCR Platform</h1>
          <p style={{ margin: '0.25rem 0 0 0', color: '#718096' }}>Deterministic multi-service pipeline for supplier invoice processing</p>
        </div>
        <div>
          <span style={{ fontSize: '0.875rem', color: '#718096' }}>API: </span>
          <strong style={{ color: health === 'healthy' ? '#38a169' : '#e53e3e' }}>{health}</strong>
        </div>
      </header>

      <section style={{ background: '#f7fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1.5rem', marginBottom: '2rem' }}>
        <h2 style={{ marginTop: 0, fontSize: '1.25rem' }}>Upload Supplier Invoice</h2>
        <form onSubmit={handleUpload} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <input
              id="receipt-upload-input"
              type="file"
              accept="image/*,.pdf"
              onChange={handleFileChange}
              style={{ flex: 1 }}
            />
            <button
              type="submit"
              disabled={!selectedFile || isUploading}
              style={{
                padding: '0.6rem 1.25rem',
                backgroundColor: isUploading ? '#a0aec0' : '#3182ce',
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                cursor: isUploading ? 'not-allowed' : 'pointer',
                fontWeight: 500
              }}
            >
              {isUploading ? 'Uploading...' : 'Upload & Extract'}
            </button>
          </div>

          {statusMessage && (
            <div style={{ padding: '0.75rem', backgroundColor: '#ebf8ff', color: '#2b6cb0', borderRadius: '6px', fontSize: '0.9rem' }}>
              {statusMessage}
            </div>
          )}
          {errorMessage && (
            <div style={{ padding: '0.75rem', backgroundColor: '#fff5f5', color: '#c53030', borderRadius: '6px', fontSize: '0.9rem' }}>
              {errorMessage}
            </div>
          )}
        </form>
      </section>

      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0, fontSize: '1.25rem' }}>Supplier Receipts Ledger</h2>
          <button
            onClick={fetchReceipts}
            style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem', backgroundColor: '#edf2f7', border: '1px solid #cbd5e0', borderRadius: '4px', cursor: 'pointer' }}
          >
            Refresh
          </button>
        </div>

        {receipts.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', backgroundColor: '#f7fafc', borderRadius: '8px', color: '#718096' }}>
            No receipts processed yet. Upload an invoice scan above to start the extraction pipeline.
          </div>
        ) : (
          <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
              <thead style={{ backgroundColor: '#edf2f7' }}>
                <tr>
                  <th style={{ padding: '0.75rem 1rem' }}>ID / Supplier</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Date</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Amount</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {receipts.map((r, idx) => (
                  <tr key={r.id} style={{ borderTop: '1px solid #e2e8f0', backgroundColor: idx % 2 === 0 ? '#fff' : '#f9fafb' }}>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <div style={{ fontWeight: 600 }}>{r.supplier_name || 'Extracting...'}</div>
                      <div style={{ fontSize: '0.75rem', color: '#a0aec0' }}>{r.id}</div>
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>{r.receipt_date || '—'}</td>
                    <td style={{ padding: '0.75rem 1rem', fontWeight: 500 }}>
                      {r.total_amount > 0 ? `${r.total_amount.toFixed(2)} ${r.currency}` : '—'}
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span style={{
                        padding: '0.2rem 0.5rem',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor:
                          r.status === 'APPROVED' ? '#c6f6d5' :
                          r.status === 'REVIEW_REQUIRED' ? '#feebc8' :
                          r.status === 'FAILED' ? '#fed7d7' : '#e2e8f0',
                        color:
                          r.status === 'APPROVED' ? '#22543d' :
                          r.status === 'REVIEW_REQUIRED' ? '#7b341e' :
                          r.status === 'FAILED' ? '#742a2a' : '#4a5568',
                      }}>
                        {r.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      {r.status === 'REVIEW_REQUIRED' && (
                        <button
                          onClick={() => handleApprove(r.id)}
                          style={{
                            padding: '0.3rem 0.6rem',
                            fontSize: '0.8rem',
                            backgroundColor: '#38a169',
                            color: '#fff',
                            border: 'none',
                            borderRadius: '4px',
                            cursor: 'pointer'
                          }}
                        >
                          Approve
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
