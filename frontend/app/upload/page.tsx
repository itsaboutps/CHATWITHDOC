"use client";
import { useState } from 'react';
import axios from 'axios';
import Link from 'next/link';
import { FileDropzone } from '../components/FileDropzone';
import { useToasts } from '../components/ToastProvider';

export default function UploadPage() {
  const [files, setFiles] = useState<FileList | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const { push } = useToasts();

  const backend = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

  const handleUpload = async () => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        const form = new FormData();
        form.append('file', f);
        const res = await axios.post(`${backend}/upload`, form, { headers: { 'Content-Type': 'multipart/form-data' } });
        setLogs(l => [...l, `Uploaded ${f.name} -> task ${res.data.task_id}`]);
      }
      setLogs(l => [...l, 'All files queued. Switch to Chat to ask once statuses become ingested.']);
      push({message:'Files queued for ingestion', type:'success'});
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className="p-6 max-w-2xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Upload Documents</h1>
      <FileDropzone onFiles={(f: any)=> setFiles(f)} />
      <input multiple type="file" onChange={e => setFiles(e.target.files)} className="border p-2 rounded w-full" />
      <div className="flex gap-3">
        <button onClick={handleUpload} disabled={uploading} className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50">{uploading ? 'Uploading...' : 'Upload'}</button>
        <Link href="/chat" className="px-4 py-2 bg-green-600 text-white rounded">Go to Chat</Link>
      </div>
      <div className="bg-white p-4 rounded shadow space-y-2 max-h-80 overflow-auto">
        {logs.map((l, i) => <div key={i} className="text-sm">{l}</div>)}
      </div>
    </main>
  );
}
