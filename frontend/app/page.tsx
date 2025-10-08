"use client";
import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { useToasts } from './components/ToastProvider';
import { ChatContainer } from './components/ChatContainer';
import { ChatInput } from './components/ChatInput';
import { DocumentSidebar } from './components/DocumentSidebar';
import { FileDropzone } from './components/FileDropzone';
import { CenterLoader } from './components/CenterLoader';

interface Message { role: 'user' | 'assistant'; content: string; sources?: string[]; answer_type?: string; document_ids_used?: number[]; error?: boolean; }
interface DocumentItem { id: number; filename: string; status: string; }
interface Health { status: string; components: Record<string,string>; }

export default function HomeUnified() {
	const [messages, setMessages] = useState<Message[]>([]);
	const [question, setQuestion] = useState('');
	const [documents, setDocuments] = useState<DocumentItem[]>([]);
	const [selectedDocs, setSelectedDocs] = useState<number[]>([]);
	const [loadingSummary, setLoadingSummary] = useState(false);
	const [loadingAnswer, setLoadingAnswer] = useState(false);
	const { push } = useToasts();
	const [uploading, setUploading] = useState(false);
	const [deleting, setDeleting] = useState<number|null>(null);
	const [activeAnswerDocs, setActiveAnswerDocs] = useState<number[]>([]);
	const [health, setHealth] = useState<Health|null>(null);
	const [pendingTasks, setPendingTasks] = useState<Record<number,string>>({});
	const [ingesting, setIngesting] = useState(false);
	const [diagnostics, setDiagnostics] = useState<any|null>(null);
	const [geminiStatus, setGeminiStatus] = useState<{active:boolean; last_error?:string|null}>({active:false});
	const [enterStreams,setEnterStreams]=useState(true);
	const [resetting,setResetting]=useState(false);
	const backend = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
	const bottomRef = useRef<HTMLDivElement | null>(null);

	const refreshDocuments = async () => { try { const res = await axios.get(`${backend}/documents`); setDocuments(res.data); } catch {} };
	const refreshDiagnostics = async () => { try { const res = await axios.get(`${backend}/diagnostics`); setDiagnostics(res.data); setGeminiStatus({active: res.data?.gemini?.active, last_error: res.data?.gemini?.last_error}); } catch {} };
	const refreshHealth = async () => { try { const res = await axios.get(`${backend}/health`); setHealth(res.data); } catch {} };
	useEffect(()=>{ let interval: any; const loop=()=>{refreshDocuments(); refreshHealth(); refreshDiagnostics();}; const schedule=()=>{ clearInterval(interval); interval = setInterval(loop, ingesting? 1200 : 5000); }; loop(); schedule(); return ()=> clearInterval(interval); },[ingesting]);
	useEffect(()=>{ setIngesting(documents.some(d=> d.status!=='ingested' && d.status!=='error')); },[documents]);
	// Prune selected docs that no longer exist (avoids stale 'Waiting...' state after refresh)
	useEffect(()=>{
		setSelectedDocs(prev => prev.filter(id => documents.some(d => d.id === id)));
	}, [documents]);

	const toggleDoc = (id:number)=> setSelectedDocs(p=> p.includes(id)? p.filter(x=>x!==id): [...p,id]);

	const ask = async (qOverride?:string) => {
		const q = (qOverride ?? question).trim(); if(!q) return;
		if(ingesting){ push({message:'Please wait - documents still processing', type:'info'}); return; }
		setMessages(m=>[...m,{role:'user',content:q}]); if(!qOverride) setQuestion(''); setLoadingAnswer(true);
		try { const res = await axios.post(`${backend}/ask`, {question:q, document_ids: selectedDocs.length? selectedDocs: undefined});
			setMessages(m=>[...m,{role:'assistant', content: res.data.answer, sources: res.data.sources, answer_type: res.data.answer_type, document_ids_used: res.data.document_ids_used, embed_mode: res.data.embed_mode, generation_mode: res.data.generation_mode}]);
			setActiveAnswerDocs(res.data.document_ids_used||[]);
		} catch { push({message:'Ask failed', type:'error'}); setMessages(m=>[...m,{role:'assistant',content:'Error: unable to get answer.',answer_type:'out_of_scope'}]); }
		finally { setLoadingAnswer(false); }
	};

	const summarize = async () => { if(selectedDocs.length!==1) return alert('Select exactly one document'); const id=selectedDocs[0]; const doc = documents.find(d=>d.id===id); if(!doc || doc.status!=='ingested'){ push({message:'Document still ingesting', type:'info'}); return; } setLoadingSummary(true); try { const res = await axios.get(`${backend}/summarize/${id}`); setMessages(m=>[...m,{role:'assistant',content:res.data.answer,sources:res.data.sources,answer_type:res.data.answer_type}]); } finally { setLoadingSummary(false); } };

	const handleFiles = useCallback(async (files: FileList | File[]) => { const arr = Array.from(files as any) as File[]; if(!arr.length) return; setUploading(true); for(const f of arr){ const form = new FormData(); form.append('file', f); try { const resp = await axios.post(`${backend}/upload`, form, { headers: {'Content-Type':'multipart/form-data'}}); if(resp.data?.task_id && resp.data.task_id!=='sync'){ setPendingTasks(p=>({...p, [resp.data.document_id]: resp.data.task_id})); } push({message:`Uploaded ${f.name}`, type:'success'}); } catch { push({message:`Upload failed: ${f.name}`, type:'error'}); } } setUploading(false); refreshDocuments(); },[backend,push]);

	// Poll for ingestion completion
	useEffect(()=>{ const iv = setInterval(async ()=>{ for(const [docId, taskId] of Object.entries(pendingTasks)){ try { const r = await axios.get(`${backend}/tasks/${taskId}`); const st = r.data?.status; if(st && st!=='PENDING' && st!=='STARTED'){ refreshDocuments(); setPendingTasks(p=>{ const cp={...p}; delete cp[Number(docId)]; return cp; }); } } catch {} } }, 3000); return ()=>clearInterval(iv); },[pendingTasks]);

	const deleteDoc = async (id:number) => { if(!confirm('Delete this document?')) return; try { await axios.delete(`${backend}/documents/${id}`); push({message:'Deleted', type:'info'}); } catch { push({message:'Delete failed', type:'error'});} finally { refreshDocuments(); } };

	const resetAll = async () => {
		if(!confirm('This will clear documents, vectors, uploads and runtime key. Continue?')) return;
		setResetting(true);
		try {
			const resp = await axios.post(`${backend}/admin/reset?token=${encodeURIComponent('')}`);
			const ok = resp.data?.success;
			const stats = resp.data?.retrieval_stats;
			setMessages([]); setSelectedDocs([]); setActiveAnswerDocs([]);
			if(ok && stats?.vectors===0 && stats?.lexical_chunks===0){
				push({message:'Pipeline fully reset', type:'success'});
			}else{
				push({message:'Reset partial - check backend logs', type:'info'});
			}
			refreshDocuments(); refreshDiagnostics();
		}
		catch { push({message:'Reset failed', type:'error'}); }
		finally { setResetting(false); }
	};

	const STAGE_LABEL: Record<string,string> = { downloading:'Downloading', parsing:'Parsing', chunking:'Chunking', embedding:'Embedding', indexing:'Indexing', uploaded:'Queued', ingested:'Ready', error:'Error' };
	const docChip = (d:DocumentItem) => { const used = activeAnswerDocs.includes(d.id); const pending = pendingTasks[d.id]; const processing = !['ingested','error'].includes(d.status); const color = d.status==='ingested'?'bg-green-500': d.status==='error'? 'bg-red-500': 'bg-amber-500'; return (
		<div key={d.id} className={`flex items-center gap-1 px-2 py-1 rounded-full text-[10px] border ${used? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/40':'border-gray-300 dark:border-gray-700'} ${processing?'opacity-75':''}`} title={d.status}>
			<span className={`w-2 h-2 rounded-full ${color} ${processing?'animate-pulse':''}`}></span>
			<span className="max-w-[120px] truncate" title={d.filename}>{d.filename}</span>
			{processing && <span className="text-[8px] text-gray-500 flex items-center gap-1">{STAGE_LABEL[d.status]||d.status}<span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-ping"/></span>}
			{pending && <span className="text-[8px] text-gray-400">task…</span>}
			<button onClick={()=>deleteDoc(d.id)} className="ml-1 text-gray-400 hover:text-red-500">×</button>
		</div>
	); };

	useEffect(()=>{ bottomRef.current?.scrollIntoView({behavior:'smooth'}); },[messages]);

	return (
		<main className="relative h-[calc(100vh-3.5rem)] max-w-full flex flex-col md:flex-row">
			<div className="w-full md:w-72 border-b md:border-b-0 md:border-r bg-white dark:bg-gray-900 flex flex-col">
				<div className="p-3 space-y-3">
					<FileDropzone onFiles={handleFiles} />
					<button onClick={resetAll} disabled={resetting} className="w-full text-[10px] px-2 py-1.5 rounded bg-red-600 text-white disabled:opacity-50 hover:bg-red-500">{resetting? 'Resetting…':'Reset / Clear All'}</button>
					<div>
						<label className="block text-[10px] font-semibold uppercase tracking-wide text-gray-500 mb-1">Pick Files</label>
						<input type="file" multiple onChange={e=>{ if(e.target.files) handleFiles(e.target.files); }} className="text-xs" />
					</div>
					{uploading && <div className="text-[10px] text-indigo-600 animate-pulse">Uploading…</div>}
					<div className="flex flex-wrap gap-2">{documents.map(docChip)}</div>
					<div className="pt-2">
						{(() => { const doc = documents.find(d=>d.id===selectedDocs[0]); const label = loadingSummary ? 'Summarizing…' : (selectedDocs.length!==1 ? 'Summarize Selected' : (!doc ? 'Select Again' : (doc.status!=='ingested' ? 'Waiting…' : 'Summarize Selected'))); return (
							<button onClick={summarize} disabled={loadingSummary || selectedDocs.length!==1 || !doc || (doc && doc.status!=='ingested')} className="w-full text-xs px-3 py-2 rounded bg-indigo-600 text-white disabled:opacity-50">{label}</button>
						); })()}
					</div>
				</div>
				<div className="flex-1 overflow-auto hidden md:block">
					<DocumentSidebar docs={documents} selected={selectedDocs} toggle={toggleDoc} />
				</div>
			</div>
			<div className="flex-1 flex flex-col min-w-0 bg-white/70 dark:bg-gray-900/60 backdrop-blur-xl">
				<div className="border-b px-4 py-2 flex items-center gap-3 text-[11px] flex-wrap">
					<span className="font-medium">Docs:</span>
					<div className="flex gap-1 flex-wrap">{documents.filter(d=>selectedDocs.includes(d.id)).map(d=> <span key={d.id} className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 text-[10px]">{d.filename}</span>)}</div>
					<span className="ml-auto flex items-center gap-2 text-gray-400">Ingested {documents.filter(d=>d.status==='ingested').length}/{documents.length}{ingesting && <span className="flex items-center gap-1 text-amber-500"><span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"/>Processing</span>}</span>
					{geminiStatus && <span className={`flex items-center gap-1 ${geminiStatus.active? 'text-indigo-600':'text-gray-400'}`} title={geminiStatus.last_error? `Last error: ${geminiStatus.last_error}`: geminiStatus.active? 'Gemini key active':'No Gemini key'}>⚡ {geminiStatus.active? 'Gemini':'No-Key'}{geminiStatus.last_error && <span className="text-red-500">!</span>}</span>}
				</div>
				<ChatContainer messages={messages} />
				<div className="border-t p-4 bg-white dark:bg-gray-900">
					<ChatInput onSend={(q)=>ask(q)} disabled={documents.length===0 || ingesting || selectedDocs.some(id=> documents.find(d=>d.id===id)?.status!=='ingested')} />
					<div className="mt-2 text-[11px] text-gray-500 flex gap-4 flex-wrap items-center">
						<span>Selected: {selectedDocs.length || 'none'}</span>
						<span>Answer uses: {activeAnswerDocs.length || '0'}</span>
						{loadingAnswer && <span className="flex items-center gap-1 text-indigo-500"><span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping"/>Loading answer…</span>}
						{ingesting && !loadingAnswer && <span className="flex items-center gap-1 text-amber-500"><span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"/>Ingesting…</span>}
						{health && <span className={`flex items-center gap-1 ${health.status==='ok'?'text-green-600':'text-red-500'}`} title={Object.entries(health.components).map(([k,v])=>`${k}:${v}`).join('\n')}>● {health.status}</span>}
						<span className="hidden sm:inline ml-auto">Tip: Shift+Enter for newline</span>
					</div>
				</div>
			</div>
		<CenterLoader visible={loadingAnswer} />
		</main>
	);
}
