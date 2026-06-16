import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './components/Sidebar'
import { AskPage } from './pages/AskPage'
import { RetrievalInspectorPage } from './pages/RetrievalInspectorPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { EvaluationPage } from './pages/EvaluationPage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { ExperimentsPage } from './pages/ExperimentsPage'
import { HallucinationDashboardPage } from './pages/HallucinationDashboardPage'
import { PromptRegistryPage } from './pages/PromptRegistryPage'
import { SystemStatusPage } from './pages/SystemStatusPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000,
    },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex h-screen overflow-hidden bg-surface-900 text-slate-100">
          <Sidebar />
          <main className="flex-1 overflow-hidden">
            <Routes>
              <Route path="/" element={<AskPage />} />
              <Route path="/retrieval" element={<RetrievalInspectorPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/evaluations" element={<EvaluationPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/experiments" element={<ExperimentsPage />} />
              <Route path="/hallucination" element={<HallucinationDashboardPage />} />
              <Route path="/prompts" element={<PromptRegistryPage />} />
              <Route path="/system" element={<SystemStatusPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
