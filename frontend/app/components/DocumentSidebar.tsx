"use client";
import React from 'react';

export interface DocItem { id: number; filename: string; status: string }

export function DocumentSidebar({ docs, selected, toggle, loading }: { docs: DocItem[]; selected: number[]; toggle: (id:number)=>void; loading?: boolean }) {
  return (
    <div className="h-full flex flex-col">
      <div className="px-4 pt-4 pb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Documents</div>
      <div className="flex-1 overflow-auto px-2 pb-4 space-y-1 custom-scroll">
        {docs.length === 0 && (
          <div className="text-xs text-gray-400 px-2 py-4 text-center">No documents yet. Upload first.</div>
        )}
        {docs.map(d => {
          const ing = d.status !== 'ingested';
          const active = selected.includes(d.id);
          return (
            <button key={d.id} onClick={()=>toggle(d.id)} className={`group w-full text-left px-3 py-2 rounded-lg border flex flex-col gap-1 transition ${active? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10':'border-transparent bg-gray-50 hover:border-gray-300 dark:bg-gray-800/40'} ${ing? 'opacity-70':''}`}>
              <div className="flex items-center gap-2 text-sm font-medium truncate">
                <span className={`w-2 h-2 rounded-full ${d.status==='ingested'?'bg-green-500':'bg-amber-400 animate-pulse'}`}></span>
                <span className="truncate flex-1" title={d.filename}>{d.filename}</span>
              </div>
              <div className="text-[10px] uppercase tracking-wide text-gray-500 flex justify-between">
                <span>{d.status}</span>
                {active && <span className="text-indigo-500">selected</span>}
              </div>
            </button>
          );
        })}
      </div>
      <div className="px-4 py-3 border-t text-[11px] text-gray-500 space-y-1">
        <div><strong>{docs.filter(d=>d.status==='ingested').length}</strong> ingested / {docs.length}</div>
        {loading && <div className="animate-pulse">Refreshing…</div>}
      </div>
    </div>
  );
}
