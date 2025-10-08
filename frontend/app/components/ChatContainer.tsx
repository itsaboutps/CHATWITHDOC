import React, { useEffect, useRef } from 'react';
import { MessageBubble, MessageBubbleProps } from './MessageBubble';

export interface ChatMessage extends MessageBubbleProps {}

export function ChatContainer({ messages }: { messages:ChatMessage[] }) {
  const bottomRef = useRef<HTMLDivElement|null>(null);
  useEffect(()=>{ bottomRef.current?.scrollIntoView({behavior:'smooth'}); },[messages]);
  return (
    <div className="flex-1 overflow-auto px-6 py-8 space-y-6 custom-scroll" id="chat-scroll">
      {messages.length===0 && (
        <div className="h-full flex items-center justify-center text-sm text-gray-400">
          Start by asking a question about an ingested document.
        </div>
      )}
  {messages.map((m,i)=>(<MessageBubble key={i} role={m.role} content={m.content} sources={m.sources} answer_type={m.answer_type} document_ids_used={m.document_ids_used} embed_mode={(m as any).embed_mode} generation_mode={(m as any).generation_mode} />))}
      <div ref={bottomRef} />
    </div>
  );
}
