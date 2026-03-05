import { Link, Route, Routes } from 'react-router-dom'
import { LibraryPage } from './pages/LibraryPage'
import { PaperDetailPage } from './pages/PaperDetailPage'

export default function App() {
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <header className="app-header">
        <div className="header-inner">
          <Link to="/" className="brand">PaperDesk</Link>
          <p className="brand-subline">Personal Paper Manager</p>
        </div>
      </header>
      <main id="main-content" className="app-main" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<LibraryPage />} />
          <Route path="/papers/:paperId" element={<PaperDetailPage />} />
        </Routes>
      </main>
    </div>
  )
}
