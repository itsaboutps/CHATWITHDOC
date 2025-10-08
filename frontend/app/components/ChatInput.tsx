"use client";
import React, { useState, useRef, useEffect } from 'react';

export function ChatInput({ onSend, disabled, placeholder }: { onSend:(msg:string)=>void; disabled?:boolean; placeholder?:string }) {
  const [value,setValue]=useState('');
  const ref=useRef<HTMLTextAreaElement|null>(null);
  useEffect(()=>{ if(ref.current){ ref.current.style.height='auto'; ref.current.style.height=Math.min(ref.current.scrollHeight,200)+"px"; }},[value]);
  const send=()=>{ if(!value.trim()) return; const q=value.trim(); setValue(''); onSend(q); };
  return (
    <div className="flex items-end gap-3 w-full">
      <div className="flex-1 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-xl px-3 py-2 focus-within:ring-2 focus-within:ring-indigo-400 transition shadow-sm">
        <textarea
          ref={ref}
          rows={1}
            value={value}
            disabled={disabled}
            placeholder={placeholder||'Ask something about your documents'}
            onChange={e=>setValue(e.target.value)}
            onKeyDown={e=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); send(); } }}
            className="w-full bg-transparent outline-none resize-none text-sm leading-relaxed"
        />
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={send} disabled={disabled} className="px-3 py-1.5 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50" title="Enter = Send (Shift+Enter newline)">Send</button>
        </div>
      </div>
    </div>
  );
}
