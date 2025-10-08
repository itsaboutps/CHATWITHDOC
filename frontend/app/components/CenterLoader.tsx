"use client";
import React from 'react';

export function CenterLoader({visible,label}:{visible:boolean; label?:string}){
  if(!visible) return null;
  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none select-none">
      <div className="flex flex-col items-center gap-3 bg-white/80 dark:bg-gray-900/70 backdrop-blur-md px-6 py-5 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 animate-fade-in">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-600" />
          </span>
          {label || 'Generating answer...'}
        </div>
        <div className="h-1 w-40 overflow-hidden rounded bg-indigo-100 dark:bg-indigo-800">
          <div className="h-full w-full origin-left animate-[shimmer_1.2s_linear_infinite] bg-gradient-to-r from-indigo-400 via-indigo-600 to-indigo-400" />
        </div>
        <style jsx>{`
          @keyframes shimmer { from { transform: scaleX(0); } to { transform: scaleX(1); } }
          .animate-fade-in { animation: fadeIn .25s ease; }
          @keyframes fadeIn { from { opacity:0; transform: scale(.97);} to {opacity:1; transform:scale(1);} }
        `}</style>
      </div>
    </div>
  );
}