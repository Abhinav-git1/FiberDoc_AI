import { useEffect, useState } from 'react'
import AutomationsView from './AutomationsView'
import ChatView, { newChat } from './ChatView'
import { DashboardView, FindingsView, ReviewQueueView } from './Views'
import { createProject, listChats, listFindings, listProjects, reviewFinding } from './api'
import { stubChat } from './savedChat'
import type { Chat, Decision, Finding, Project } from './types'

type View = 'chat' | 'projects' | 'automations' | 'findings' | 'review'

function NavBtn({ v, label, badge, view, setView }: { v: View; label: string; badge?: number; view: View; setView: (v: View) => void }) {
  return (
    <button className={'nav-item' + (view === v ? ' active' : '')} onClick={() => setView(v)}>
      {label}{!!badge && <span className="count">{badge}</span>}
    </button>
  )
}

export default function App() {
  const [view, setView] = useState<View>('chat')
  const [chats, setChats] = useState<Chat[]>(() => [newChat()])
  const [activeId, setActiveId] = useState(chats[0].id)
  const [projects, setProjects] = useState<Project[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [projectId, setProjectId] = useState('')
  const [sideOpen, setSideOpen] = useState(true)

  const [uploadProjectId, setUploadProjectId] = useState('')
  const [loadError, setLoadError] = useState('')

  /** Reload projects + findings from the backend (also called after a document finishes processing). */
  async function refresh(): Promise<Finding[]> {
    const [p, f] = await Promise.all([listProjects(), listFindings()])
    setProjects(p)
    setFindings(f)
    setUploadProjectId((cur) => cur || p[0]?.id || '')
    return f
  }

  useEffect(() => {
    refresh().then(() => setLoadError('')).catch((e: Error) => setLoadError(e.message))
    // Saved chats go under the empty new chat; their messages load when one is opened.
    listChats()
      .then((saved) => setChats((cs) => [...cs, ...saved.filter((s) => !cs.some((c) => c.serverId === s.id)).map(stubChat)]))
      .catch(() => {}) // the error banner above already covers an unreachable backend
  }, [])

  async function onCreateProject(name: string, location: string) {
    const p = await createProject(name, location)
    await refresh()
    setUploadProjectId(p.id)
  }

  async function onReview(id: string, decision: Decision, comment: string) {
    const updated = await reviewFinding(id, decision, comment)
    setFindings((fs) => fs.map((f) => (f.id === id ? updated : f)))
  }

  function startNewChat() {
    const c = newChat()
    setChats((cs) => [c, ...cs])
    setActiveId(c.id)
    setView('chat')
  }

  const pendingCount = findings.filter((f) => f.decision === 'pending').length

  return (
    <div className="app">
      {sideOpen && (
        <aside className="sidebar">
          <div className="brand"><span className="logo">◎</span> FiberDoc AI</div>
          <button className="new-chat" onClick={startNewChat}>＋ New chat</button>
          <nav className="nav">
            <NavBtn v="chat" label="💬 Chat & upload" view={view} setView={setView} />
            <NavBtn v="projects" label="🗂 Projects" view={view} setView={setView} />
            <NavBtn v="automations" label="⚡ Automations" view={view} setView={setView} />
            <NavBtn v="findings" label="🔍 Findings" view={view} setView={setView} />
            <NavBtn v="review" label="✅ Review queue" badge={pendingCount} view={view} setView={setView} />
          </nav>
          {/* Shown on every page: picking a chat from Projects/Findings/Review goes back to the chat view. */}
          <div className="history-label">Recent chats</div>
          <nav className="history">
            {chats.map((c) => (
              <button key={c.id} className={'history-item' + (view === 'chat' && c.id === activeId ? ' active' : '')}
                onClick={() => { setActiveId(c.id); setView('chat') }}>
                {c.title}
              </button>
            ))}
          </nav>
          <div className="side-foot">Engineer · Demo workspace</div>
        </aside>
      )}

      <main className="main">
        <header className="topbar">
          <button className="icon-btn" title="Toggle sidebar" onClick={() => setSideOpen((s) => !s)}>☰</button>
          <span className="topbar-title">
            {{ chat: chats.find((c) => c.id === activeId)?.title, projects: 'Projects', automations: 'Automations', findings: 'Findings', review: 'Review queue' }[view]}
          </span>
        </header>

        <div className="banner demo">Demo rule catalogue: non-authoritative. These are invented example requirements, not official telecom or regulatory standards.</div>

        {/* Chat stays mounted so uploads/OCR keep running when switching views. */}
        {loadError && <div className="banner err">{loadError}</div>}
        <div className="view" hidden={view !== 'chat'}>
          <ChatView chats={chats} setChats={setChats} activeId={activeId}
            projects={projects} uploadProjectId={uploadProjectId} setUploadProjectId={setUploadProjectId}
            refresh={refresh} goTo={setView} findings={findings} onReview={onReview} />
        </div>
        {view === 'projects' && (
          <div className="view">
            <DashboardView projects={projects} findings={findings} onCreateProject={onCreateProject}
              onOpenProject={(id) => { setProjectId(id); setView('findings') }} />
          </div>
        )}
        {view === 'automations' && (
          <div className="view"><AutomationsView /></div>
        )}
        {view === 'findings' && (
          <div className="view">
            <FindingsView projects={projects} findings={findings} onReview={onReview} projectId={projectId} setProjectId={setProjectId} />
          </div>
        )}
        {view === 'review' && (
          <div className="view"><ReviewQueueView findings={findings} onReview={onReview} /></div>
        )}
      </main>
    </div>
  )
}
