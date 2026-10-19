import { useEffect, useState } from 'react';
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Activity, ArrowRight, BookOpen, CalendarClock, Coffee, Compass, LayoutDashboard, LogOut, Settings2, ShieldCheck, Users } from 'lucide-react';
import { api } from './api';
import { finishSignIn, signIn } from './auth';
import { Badge, ErrorBox, Loading } from './components';
import { Dashboard, Discovery, Jobs, JobProgress, Candidates, Followups, AuditLog, Settings, Health } from './pages';
import CandidateDetail from './CandidateDetail';
import type { Config } from './types';

function Login({config}: {config: Config}) {
  const navigate = useNavigate(); const [error,setError] = useState<Error | null>(null);
  return <div className="login"><div className="login-brand"><Coffee size={40}/><span>QIMA <small>COFFEE</small></span></div><p className="eyebrow">DISCOVERY & OUTREACH</p><h1>Good coffee starts<br/>with good connections.</h1><p>One workspace to discover buyers, build sourcing relationships, and turn evidence into your next conversation.</p>{config.auth_mode === 'local' ? <><Badge tone="amber">LOCAL DEVELOPMENT · FICTIONAL DEMO DATA</Badge><button className="primary" onClick={() => {sessionStorage.setItem('local_access','yes'); navigate('/');}}>Enter local workspace <ArrowRight size={18}/></button></> : <button className="primary" onClick={() => signIn().catch(setError)}>Sign in securely <ArrowRight size={18}/></button>}<ErrorBox error={error}/><span className="login-footer">Research with context. Relationships with care.</span></div>;
}
function Callback() { const navigate = useNavigate();const [error,setError] = useState<Error | null>(null);useEffect(() => {finishSignIn().then(() => navigate('/',{replace:true})).catch(setError);},[navigate]);return <><Loading/><ErrorBox error={error}/></>; }

export default function App() {
  const config = useQuery({queryKey:['config'],queryFn:() => api<Config>('/api/config')});
  if (config.isPending) return <Loading/>;
  if (config.error) return <main><ErrorBox error={config.error}/><p>Start the API on localhost:8000, then refresh this page.</p></main>;
  return <Routes><Route path="/login" element={<Login config={config.data}/>}/><Route path="/callback" element={<Callback/>}/><Route path="*" element={<Workspace config={config.data}/>}/></Routes>;
}
function Workspace({config}: {config: Config}) {
  const authenticated = config.auth_mode === 'local' ? sessionStorage.getItem('local_access') : sessionStorage.getItem('access_token');
  if (!authenticated) return <Navigate to="/login" replace/>;
  const links = [{to:'/',label:'Overview',icon:LayoutDashboard},{to:'/agents',label:'Discover',icon:Compass},{to:'/candidates',label:'Candidates',icon:Users},{to:'/jobs',label:'Search activity',icon:Activity},{to:'/followups',label:'Follow-ups',icon:CalendarClock},{to:'/audit',label:'Audit trail',icon:BookOpen},{to:'/settings',label:'Scoring policies',icon:Settings2},{to:'/health',label:'System status',icon:ShieldCheck}];
  return <div className="workspace"><a href="#main" className="skip-link">Skip to content</a><aside className="sidebar"><Link to="/" className="brand"><Coffee size={30}/><span>QIMA<small>COFFEE</small></span></Link><div className="workspace-label">RELATIONSHIP WORKSPACE</div><nav aria-label="Main navigation">{links.map(l => <NavLink to={l.to} end={l.to === '/'} key={l.to}><l.icon size={19}/>{l.label}</NavLink>)}</nav><div className="sidebar-note"><span className="status-dot"/> Human-led, evidence-informed<p>Every conversation starts<br/>with your approval.</p></div><div className="sidebar-user"><span className="avatar">QC</span><div><strong>Qima workspace</strong><small>{config.auth_mode === 'local' ? 'Development access' : 'Authenticated access'}</small></div><button className="icon-button" aria-label="Sign out" onClick={() => {sessionStorage.clear();location.assign('/login');}}><LogOut size={17}/></button></div></aside><div className="content-shell"><header className="topbar"><span>Discovery & Outreach <span className="topbar-divider">/</span> <strong>Workspace</strong></span><Badge tone="green"><span className="status-dot"/>{config.mode}</Badge></header><div className="mode-banner"><ShieldCheck size={15}/><strong>{config.discovery}</strong><span>{config.auth_mode === 'local' ? 'Development access · ' : ''}Email is simulated. Instagram first-touch is manual.</span></div><main id="main"><Routes><Route path="/" element={<Dashboard/>}/><Route path="/agents" element={<Dashboard chooseOnly/>}/><Route path="/discover" element={<Discovery/>}/><Route path="/jobs" element={<Jobs/>}/><Route path="/jobs/:id" element={<JobProgress/>}/><Route path="/candidates" element={<Candidates/>}/><Route path="/candidates/:id" element={<CandidateDetail/>}/><Route path="/followups" element={<Followups/>}/><Route path="/audit" element={<AuditLog/>}/><Route path="/settings" element={<Settings/>}/><Route path="/health" element={<Health/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></main><footer className="page-footer">Qima Coffee <span>Discovery is a beginning. People build the relationship.</span></footer></div></div>;
}
