"use client";
import Link from 'next/link';
import { useState, useEffect } from 'react';
import { useToasts } from './ToastProvider';

export function Navbar() {
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
  const { push } = useToasts();
  const [geminiKey, setGeminiKey] = useState('');
  const [active, setActive] = useState(false);

  const refresh = async () => {
    try { const r = await fetch(`${backend}/gemini/key`); if(r.ok){ const js = await r.json(); setActive(!!js.active);} } catch {}
  };
  useEffect(()=>{ refresh(); }, []);

  const apply = async () => {
    if(!geminiKey.trim()) { push({message:'Enter a key first', type:'error'}); return; }
    const r = await fetch(`${backend}/gemini/key`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({key: geminiKey.trim()})});
    if(r.ok){ setGeminiKey(''); refresh(); push({message:'Gemini key set', type:'success'});} else push({message:'Failed to set key', type:'error'});
  };
  const clear = async () => { await fetch(`${backend}/gemini/key`, {method:'DELETE'}); refresh(); push({message:'Gemini key cleared', type:'info'}); };

  return (
    <nav className="sticky top-0 z-40 backdrop-blur bg-white/70 border-b border-gray-200 dark:bg-gray-900/70 dark:border-gray-700">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-6">
        <Link href="/" className="font-semibold text-lg tracking-tight">DocQ&A</Link>
        <div className="hidden sm:flex gap-4 text-sm text-gray-500">
          <span className="italic">Unified Workspace</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <input type="password" placeholder="Gemini key" value={geminiKey} onChange={e=>setGeminiKey(e.target.value)} className="px-2 py-1 text-xs rounded border border-gray-300 focus:outline-none focus:ring focus:ring-indigo-300" />
          <button onClick={apply} className="text-xs px-2 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-500">Set</button>
          <button onClick={clear} className="text-xs px-2 py-1 rounded bg-gray-300 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 dark:text-gray-100">Clear</button>
          <span className={`text-xs font-medium ${active? 'text-green-600':'text-red-500'}`}>{active? 'Key Active':'No Key'}</span>
        </div>
      </div>
    </nav>
  );
}
