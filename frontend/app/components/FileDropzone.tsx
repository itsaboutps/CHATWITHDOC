"use client";
import { useCallback, useState } from 'react';

interface Props { onFiles: (files: FileList | File[]) => void }

export function FileDropzone({ onFiles }: Props) {
  const [active, setActive] = useState(false);
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setActive(false);
    if(e.dataTransfer.files && e.dataTransfer.files.length>0) {
      onFiles(e.dataTransfer.files);
    }
  }, [onFiles]);
  return (
    <div
      onDragOver={e=>{ e.preventDefault(); setActive(true);} }
      onDragLeave={e=>{ e.preventDefault(); setActive(false);} }
      onDrop={onDrop}
      className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors text-sm cursor-pointer select-none ${active? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30':'border-gray-300 dark:border-gray-600'}`}
    >
      <p className="font-medium">Drag & Drop files here</p>
      <p className="text-xs text-gray-500 mt-1">or use the picker below</p>
    </div>
  );
}
