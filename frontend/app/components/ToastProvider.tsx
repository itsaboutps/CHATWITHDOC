"use client";
import { createContext, useContext, useState, useCallback, ReactNode, useEffect } from 'react';

interface Toast { id: string; message: string; type?: 'info'|'success'|'error'; timeout?: number }
interface ToastCtx { push: (t: Omit<Toast,'id'>) => void }
const ToastContext = createContext<ToastCtx | null>(null);

export function useToasts() {
  const ctx = useContext(ToastContext);
  if(!ctx) throw new Error('ToastProvider missing');
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast,'id'>) => {
    const id = Math.random().toString(36).slice(2);
    const timeout = t.timeout ?? 3500;
    setToasts(ts => [...ts, { id, ...t, timeout }]);
    if(timeout > 0) setTimeout(() => setToasts(ts => ts.filter(x => x.id !== id)), timeout);
  }, []);
  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 space-y-2 w-72">
        {toasts.map(t => (
          <div key={t.id} className={`text-sm rounded shadow-lg px-4 py-3 backdrop-blur border flex items-start gap-2 animate-fade-in
            ${t.type==='error' ? 'bg-red-600/90 text-white border-red-500' : t.type==='success' ? 'bg-green-600/90 text-white border-green-500' : 'bg-gray-800/90 text-white border-gray-700'}`}> 
            <span className="flex-1">{t.message}</span>
            <button onClick={()=>setToasts(ts=>ts.filter(x=>x.id!==t.id))} className="opacity-70 hover:opacity-100">×</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
